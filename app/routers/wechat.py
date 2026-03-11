import hashlib
import hmac
import logging
import time
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.plugins.builtin.wechat_official import load_wechat_settings


router = APIRouter(tags=["微信公众号回调"])
logger = logging.getLogger(__name__)


def _string(value: object) -> str:
    return str(value or "").strip()


def _wechat_signature(token: str, timestamp: str, nonce: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _is_valid_signature(token: str, signature: str, timestamp: str, nonce: str) -> bool:
    if not token or not signature or not timestamp or not nonce:
        return False
    expected = _wechat_signature(token, timestamp, nonce)
    return hmac.compare_digest(expected, signature)


def _parse_xml_payload(raw_xml: str) -> dict[str, str]:
    root = ET.fromstring(raw_xml)
    payload: dict[str, str] = {}
    for child in root:
        payload[child.tag] = child.text or ""
    return payload


def _wrap_cdata(value: str) -> str:
    return _string(value).replace("]]>", "]]]]><![CDATA[>")


def _build_text_reply_xml(to_user: str, from_user: str, content: str) -> str:
    now = int(time.time())
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{_wrap_cdata(to_user)}]]></ToUserName>"
        f"<FromUserName><![CDATA[{_wrap_cdata(from_user)}]]></FromUserName>"
        f"<CreateTime>{now}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{_wrap_cdata(content)}]]></Content>"
        "</xml>"
    )


def _load_callback_config(db: Session, settings: Settings) -> dict[str, str]:
    config = load_wechat_settings(db, settings)
    return {
        "token": _string(config.get("callback_token")),
        "reply_text": _string(config.get("callback_reply_text")),
        "subscribe_reply": _string(config.get("callback_subscribe_reply")) or _string(config.get("callback_reply_text")),
    }


@router.get("/wechat", response_class=PlainTextResponse)
def verify_wechat_server(
    signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    config = _load_callback_config(db, settings)
    if not config["token"]:
        return PlainTextResponse("wechat callback token not configured", status_code=503)
    if not signature or not timestamp or not nonce or not echostr:
        return PlainTextResponse("missing wechat signature parameters", status_code=400)
    if not _is_valid_signature(config["token"], signature, timestamp, nonce):
        return PlainTextResponse("invalid wechat signature", status_code=403)
    return PlainTextResponse(echostr)


@router.post("/wechat")
async def receive_wechat_message(
    request: Request,
    signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    config = _load_callback_config(db, settings)
    if not config["token"]:
        return PlainTextResponse("wechat callback token not configured", status_code=503)
    if not _is_valid_signature(config["token"], signature, timestamp, nonce):
        return PlainTextResponse("invalid wechat signature", status_code=403)

    raw_body = (await request.body()).decode("utf-8", errors="ignore").strip()
    if not raw_body:
        return PlainTextResponse("success")

    try:
        payload = _parse_xml_payload(raw_body)
    except ET.ParseError:
        return PlainTextResponse("invalid xml body", status_code=400)

    msg_type = _string(payload.get("MsgType")).lower()
    event = _string(payload.get("Event")).lower()
    from_user = _string(payload.get("FromUserName"))
    to_user = _string(payload.get("ToUserName"))
    logger.info("Received WeChat callback msg_type=%s event=%s from=%s", msg_type, event, from_user[:64])

    reply_text = ""
    if msg_type == "event" and event == "subscribe":
        reply_text = config["subscribe_reply"]
    elif msg_type == "text":
        reply_text = config["reply_text"]

    if reply_text and from_user and to_user:
        return Response(content=_build_text_reply_xml(from_user, to_user, reply_text), media_type="application/xml")

    return PlainTextResponse("success")
