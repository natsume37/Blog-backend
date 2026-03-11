import hashlib
import asyncio
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import Base
from app.models.plugin import PluginSetting
from app.routers.wechat import receive_wechat_message, verify_wechat_server


def _build_signature(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()


def _build_db_session(tmp_path: Path):
    db_path = tmp_path / "wechat-callback.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        db.add_all([
            PluginSetting(plugin_id="wechat-official-account", key="callback_token", value="martin"),
            PluginSetting(plugin_id="wechat-official-account", key="callback_reply_text", value="已收到你的消息"),
            PluginSetting(plugin_id="wechat-official-account", key="callback_subscribe_reply", value="欢迎关注测试号"),
        ])
        db.commit()
        return TestingSessionLocal()
    finally:
        db.close()


def _build_request(body: str) -> Request:
    payload = body.encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/wechat",
        "headers": [(b"content-type", b"application/xml")],
    }
    return Request(scope, receive)


def test_wechat_verify_route_returns_echostr(tmp_path: Path) -> None:
    db = _build_db_session(tmp_path)
    timestamp = "1710000000"
    nonce = "123456"
    signature = _build_signature("martin", timestamp, nonce)
    try:
        response = verify_wechat_server(
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            echostr="hello-wechat",
            db=db,
            settings=get_settings(),
        )
    finally:
        db.close()

    assert response.status_code == 200
    assert response.body.decode("utf-8") == "hello-wechat"


def test_wechat_verify_route_rejects_invalid_signature(tmp_path: Path) -> None:
    db = _build_db_session(tmp_path)
    try:
        response = verify_wechat_server(
            signature="invalid",
            timestamp="1710000000",
            nonce="123456",
            echostr="hello-wechat",
            db=db,
            settings=get_settings(),
        )
    finally:
        db.close()

    assert response.status_code == 403
    assert "invalid wechat signature" in response.body.decode("utf-8")


def test_wechat_callback_replies_to_text_message(tmp_path: Path) -> None:
    db = _build_db_session(tmp_path)
    timestamp = "1710000000"
    nonce = "123456"
    signature = _build_signature("martin", timestamp, nonce)
    payload = """
    <xml>
      <ToUserName><![CDATA[gh_test]]></ToUserName>
      <FromUserName><![CDATA[user_openid]]></FromUserName>
      <CreateTime>1710000000</CreateTime>
      <MsgType><![CDATA[text]]></MsgType>
      <Content><![CDATA[你好]]></Content>
      <MsgId>1234567890</MsgId>
    </xml>
    """.strip()
    request = _build_request(payload)
    try:
        response = asyncio.run(receive_wechat_message(
            request=request,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            db=db,
            settings=get_settings(),
        ))
    finally:
        db.close()

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "<MsgType><![CDATA[text]]></MsgType>" in body
    assert "<Content><![CDATA[已收到你的消息]]></Content>" in body


def test_wechat_callback_replies_to_subscribe_event(tmp_path: Path) -> None:
    db = _build_db_session(tmp_path)
    timestamp = "1710000000"
    nonce = "123456"
    signature = _build_signature("martin", timestamp, nonce)
    payload = """
    <xml>
      <ToUserName><![CDATA[gh_test]]></ToUserName>
      <FromUserName><![CDATA[user_openid]]></FromUserName>
      <CreateTime>1710000000</CreateTime>
      <MsgType><![CDATA[event]]></MsgType>
      <Event><![CDATA[subscribe]]></Event>
    </xml>
    """.strip()
    request = _build_request(payload)
    try:
        response = asyncio.run(receive_wechat_message(
            request=request,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            db=db,
            settings=get_settings(),
        ))
    finally:
        db.close()

    assert response.status_code == 200
    assert "<Content><![CDATA[欢迎关注测试号]]></Content>" in response.body.decode("utf-8")
