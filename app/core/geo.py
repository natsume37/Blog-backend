from __future__ import annotations

import re


_EN_PROVINCE_TO_CN = {
    "beijing": "北京市",
    "tianjin": "天津市",
    "shanghai": "上海市",
    "chongqing": "重庆市",
    "hebei": "河北省",
    "shanxi": "山西省",
    "liaoning": "辽宁省",
    "jilin": "吉林省",
    "heilongjiang": "黑龙江省",
    "jiangsu": "江苏省",
    "zhejiang": "浙江省",
    "anhui": "安徽省",
    "fujian": "福建省",
    "jiangxi": "江西省",
    "shandong": "山东省",
    "henan": "河南省",
    "hubei": "湖北省",
    "hunan": "湖南省",
    "guangdong": "广东省",
    "hainan": "海南省",
    "sichuan": "四川省",
    "guizhou": "贵州省",
    "yunnan": "云南省",
    "shanxi sheng": "陕西省",
    "shaanxi": "陕西省",
    "gansu": "甘肃省",
    "qinghai": "青海省",
    "taiwan": "台湾省",
    "inner mongolia": "内蒙古自治区",
    "guangxi": "广西壮族自治区",
    "tibet": "西藏自治区",
    "ningxia": "宁夏回族自治区",
    "xinjiang": "新疆维吾尔自治区",
    "hong kong": "香港特别行政区",
    "macao": "澳门特别行政区",
    "macau": "澳门特别行政区",
}


def normalize_china_province_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    if re.search(r"[\u4e00-\u9fff]", raw):
        return raw

    key = (
        raw.lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace(" province", "")
        .strip()
    )
    key = " ".join(key.split())
    return _EN_PROVINCE_TO_CN.get(key, raw)
