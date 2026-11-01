# -*- coding: utf-8 -*-
"""可选的现实层天气(Open-Meteo 免费接口, 无需钥匙)。只有调用方显式给出经纬度时才会联网。"""
import json
import urllib.parse
import urllib.request


def wmo_desc(code):
    """WMO 天气码 -> 中文(按 Open-Meteo 码表)。"""
    if code == 0:
        return "晴"
    if code in (1, 2, 3):
        return "多云"
    if code in (45, 48):
        return "有雾"
    if code in (51, 53, 55):
        return "毛毛雨"
    if code in (56, 57, 66, 67):
        return "冻雨"
    if code == 61:
        return "小雨"
    if code in (63, 65):
        return "雨"
    if code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if code in (80, 81, 82):
        return "阵雨"
    if code in (95, 96, 99):
        return "雷雨"
    return "有雨" if code >= 50 else "多云"


def weather(lat, lon, timeout=8):
    """当天天气 {desc, code, tmax, tmin, rain_prob}; 失败返回 None。"""
    params = {"latitude": lat, "longitude": lon,
              "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
              "timezone": "auto", "forecast_days": 1}
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        code = int(r["daily"]["weather_code"][0])
        return {"desc": wmo_desc(code), "code": code,
                "tmax": round(r["daily"]["temperature_2m_max"][0]),
                "tmin": round(r["daily"]["temperature_2m_min"][0]),
                "rain_prob": r["daily"]["precipitation_probability_max"][0]}
    except Exception:
        return None
