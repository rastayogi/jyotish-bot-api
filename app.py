import swisseph as swe
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime

app = FastAPI(title="Jyotish Ephemeris API")
geolocator = Nominatim(user_agent="jyotish_bot_v3")
tf = TimezoneFinder()

swe.set_ephe_path('')
swe.set_sid_mode(swe.SIDM_LAHIRI)

SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
]

def format_coords(degrees_total: float):
    sign_idx = int(degrees_total // 30) % 12
    deg_in_sign = degrees_total % 30
    d = int(deg_in_sign)
    m = int((deg_in_sign - d) * 60)
    return SIGNS[sign_idx], f"{d}°{m:02d}'"

class BirthData(BaseModel):
    name: str = "Пользователь"
    date: str
    time: str
    city: str

@app.get("/")
def root():
    return {"status": "ok", "message": "Jyotish API is running"}

@app.post("/calculate")
def calculate(data: BirthData):
    try:
        clean_date = data.date.strip()
        clean_time = data.time.strip()
        clean_city = data.city.strip()
        
        loc = geolocator.geocode(clean_city, timeout=10)
        if not loc:
            short_city = clean_city.split(',')[0].strip()
            loc = geolocator.geocode(short_city, timeout=10)
            if not loc:
                raise HTTPException(status_code=400, detail=f"Город '{clean_city}' не найден")
        
        lat, lon = loc.latitude, loc.longitude
        tz_name = tf.timezone_at(lng=lon, lat=lat) or "UTC"
        local_tz = pytz.timezone(tz_name)
        
        dt_local = datetime.strptime(f"{clean_date} {clean_time}", "%d.%m.%Y %H:%M")
        dt_local = local_tz.localize(dt_local)
        dt_utc = dt_local.astimezone(pytz.utc)
        
        hour_decimal = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
        jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)
        
        houses, ascmc = swe.houses_ex(jd_ut, lat, lon, b'P', swe.FLG_SIDEREAL)
        lagna_sign, lagna_deg = format_coords(ascmc[0])
        
        planets_order = [
            ("sun", "☀️ Солнце (Сурья)", swe.SUN),
            ("moon", "🌙 Луна (Чандра)", swe.MOON),
            ("mars", "♂️ Марс (Мангала)", swe.MARS),
            ("mercury", "☿ Меркурий (Будха)", swe.MERCURY),
            ("jupiter", "♃ Юпитер (Гуру)", swe.JUPITER),
            ("venus", "♀ Венера (Шукра)", swe.VENUS),
            ("saturn", "♄ Сатурн (Шани)", swe.SATURN),
            ("rahu", "☊ Раху", swe.MEAN_NODE)
        ]
        
        lines = []
        for p_key, p_label, p_id in planets_order:
            res, _ = swe.calc_ut(jd_ut, p_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            sign, deg_str = format_coords(res[0])
            lines.append(f"{p_label} — {sign}, {deg_str}")
            
            if p_key == "rahu":
                ketu_pos = (res[0] + 180.0) % 360.0
                k_sign, k_deg = format_coords(ketu_pos)
                lines.append(f"☋ Кету — {k_sign}, {k_deg}")
        
        full_result_text = (
            f"✨ Ваш восходящий знак (Лагна): {lagna_sign} ({lagna_deg})\n\n"
            f"Положения планет в карте Раши:\n"
            f"⬆️ Асцендент — {lagna_sign}, {lagna_deg}\n" +
            "\n".join(lines)
        )
        
        return {
            "status": "success",
            "result_text": full_result_text
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
