from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import swisseph as swe
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz

app = FastAPI(title="Jyotish Ephemeris API")

# Устанавливаем сидерический зодиак и айянамшу Лахири
swe.set_sid_mode(swe.SIDM_LAHIRI)

geolocator = Nominatim(user_agent="jyotish_bot_calculator")
tf = TimezoneFinder()

ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", 
    "Лев", "Дева", "Весы", "Скорпион", 
    "Стрелец", "Козерог", "Водолей", "Рыбы"
]

PLANETS_MAP = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mars": swe.MARS,
    "mercury": swe.MERCURY,
    "jupiter": swe.JUPITER,
    "venus": swe.VENUS,
    "saturn": swe.SATURN,
    "rahu": swe.MEAN_NODE
}

class BirthDataRequest(BaseModel):
    name: str = "Пользователь"
    date: str  # Формат: DD.MM.YYYY
    time: str  # Формат: HH:MM
    city: str  # Например: "Владивосток, Россия"

def format_degrees(total_deg: float) -> tuple[str, str, float]:
    """Возвращает знак зодиака, градусы и минуты."""
    norm_deg = total_deg % 360.0
    sign_index = int(norm_deg // 30)
    sign_name = ZODIAC_SIGNS[sign_index]
    
    deg_in_sign = norm_deg % 30.0
    degrees = int(deg_in_sign)
    minutes = int(round((deg_in_sign - degrees) * 60))
    
    if minutes == 60:
        degrees += 1
        minutes = 0
        
    return sign_name, f"{degrees}°{minutes:02d}'", norm_deg

@app.post("/calculate")
async def calculate_chart(data: BirthDataRequest):
    # 1. Геокодинг
    location = geolocator.geocode(data.city, timeout=10)
    if not location:
        raise HTTPException(status_code=400, detail="Город не найден. Уточните название.")
    
    lat = location.latitude
    lon = location.longitude
    
    # 2. Определение таймзоны
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        raise HTTPException(status_code=400, detail="Не удалось определить часовой пояс.")
    
    # 3. Перевод локального времени в UTC
    try:
        local_tz = pytz.timezone(tz_name)
        dt_str = f"{data.date} {data.time}"
        naive_dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
        localized_dt = local_tz.localize(naive_dt, is_dst=None)
        utc_dt = localized_dt.astimezone(pytz.utc)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки даты/времени: {str(e)}")

    # 4. Расчет Юлианского дня (UT)
    utc_decimal_hour = utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0)
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_decimal_hour)

    # 5. Расчет Лагны (Асцендента)
    # Флаг swe.FLG_SIDEREAL применяет сидерический зодиак с выбранной айянамшей
    houses, ascmc = swe.houses_ex(jd_ut, lat, lon, b'P', swe.FLG_SIDEREAL)
    ascendant_deg = ascmc[0]
    asc_sign, asc_formatted, _ = format_degrees(ascendant_deg)

    # 6. Расчет планет
    planets_result = {}
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

    for name, planet_id in PLANETS_MAP.items():
        res, _ = swe.calc_ut(jd_ut, planet_id, flags)
        p_deg = res[0]
        p_sign, p_fmt, _ = format_degrees(p_deg)
        planets_result[name] = {
            "sign": p_sign,
            "degrees": p_fmt,
            "raw_deg": round(p_deg, 4),
            "is_retrograde": res[3] < 0
        }

    # Кету (всегда ровно напротив Раху)
    ketu_deg = (planets_result["rahu"]["raw_deg"] + 180.0) % 360.0
    k_sign, k_fmt, _ = format_degrees(ketu_deg)
    planets_result["ketu"] = {
        "sign": k_sign,
        "degrees": k_fmt,
        "raw_deg": round(ketu_deg, 4),
        "is_retrograde": True
    }

    return {
        "status": "success",
        "location": {
            "address": location.address,
            "lat": lat,
            "lon": lon,
            "timezone": tz_name
        },
        "ascendant": {
            "sign": asc_sign,
            "degrees": asc_formatted,
            "raw_deg": round(ascendant_deg, 4)
        },
        "planets": planets_result
    }
