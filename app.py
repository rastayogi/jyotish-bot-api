from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pytz
import swisseph as swe
from timezonefinder import TimezoneFinder

app = FastAPI()
tf = TimezoneFinder()

swe.set_ephe_path('')
swe.set_sid_mode(swe.SIDM_LAHIRI)

SIGNS = [
    "Овен",
    "Телец",
    "Близнецы",
    "Рак",
    "Лев",
    "Дева",
    "Весы",
    "Скорпион",
    "Стрелец",
    "Козерог",
    "Водолей",
    "Рыбы",
]

FAST_CITIES = {
    "владивосток": (43.1155, 131.8855, "Asia/Vladivostok"),
    "москва": (55.7558, 37.6173, "Europe/Moscow"),
    "санкт-петербург": (59.9343, 30.3351, "Europe/Moscow"),
    "новосибирск": (55.0084, 82.9357, "Asia/Novosibirsk"),
    "екатеринбург": (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "казань": (55.8304, 49.0661, "Europe/Moscow"),
    "минск": (53.9006, 27.5590, "Europe/Minsk"),
    "киев": (50.4501, 30.5234, "Europe/Kiev"),
    "алматы": (43.2220, 76.8512, "Asia/Almaty"),
}


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
  return {"status": "ok"}


@app.post("/calculate")
def calculate(data: BirthData):
  try:
    clean_date = data.date.strip()
    clean_time = data.time.strip()
    city_key = data.city.strip().lower().split(",")[0].strip()

    lat, lon, tz_name = FAST_CITIES.get(
        city_key, (43.1155, 131.8855, "Asia/Vladivostok")
    )

    local_tz = pytz.timezone(tz_name)
    dt_local = datetime.strptime(
        f"{clean_date} {clean_time}", "%d.%m.%Y %H:%M"
    )
    dt_local = local_tz.localize(dt_local)
    dt_utc = dt_local.astimezone(pytz.utc)

    hour_decimal = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    jd_ut = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)

    houses, ascmc = swe.houses_ex(jd_ut, lat, lon, b"P", swe.FLG_SIDEREAL)
    lagna_sign, lagna_deg = format_coords(ascmc[0])

    planets_order = [
        ("☀️ Солнце (Сурья)", swe.SUN),
        ("🌙 Луна (Чандра)", swe.MOON),
        ("♂️ Марс (Мангала)", swe.MARS),
        ("☿ Меркурий (Будха)", swe.MERCURY),
        ("♃ Юпитер (Гуру)", swe.JUPITER),
        ("♀ Венера (Шукра)", swe.VENUS),
        ("♄ Сатурн (Шани)", swe.SATURN),
        ("☊ Раху", swe.MEAN_NODE),
    ]

    lines = [f"⬆️ Асцендент — {lagna_sign}, {lagna_deg}"]
    for p_label, p_id in planets_order:
      res, _ = swe.calc_ut(jd_ut, p_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
      sign, deg_str = format_coords(res[0])
      lines.append(f"{p_label} — {sign}, {deg_str}")
      if p_id == swe.MEAN_NODE:
        ketu_pos = (res[0] + 180.0) % 360.0
        k_sign, k_deg = format_coords(ketu_pos)
        lines.append(f"☋ Кету — {k_sign}, {k_deg}")

    full_result_text = (
        f"✨ Ваш восходящий знак (Лагна): {lagna_sign} ({lagna_deg})\n\n"
        "Положения планет в карте Раши:\n" + "\n".join(lines)
    )

    return {"status": "success", "result_text": full_result_text}
  except Exception as e:
    raise HTTPException(status_code=400, detail=str(e))
