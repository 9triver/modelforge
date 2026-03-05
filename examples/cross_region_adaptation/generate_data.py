"""Generate synthetic hourly load data for East China and North China regions.

Both regions share the same 10-feature schema (unified weather monitoring), but have
distinct climate patterns, load profiles, and feature importance:
- East China: subtropical, summer AC peak, key drivers are AC index & humidity
- North China: continental, winter heating peak, key drivers are heating index & wind speed
"""

import numpy as np
import pandas as pd

# Chinese statutory holidays 2024
HOLIDAYS_2024 = {
    (1, 1),                                          # 元旦
    *{(2, d) for d in range(10, 18)},                # 春节
    (4, 4), (4, 5), (4, 6),                          # 清明
    *{(5, d) for d in range(1, 6)},                  # 劳动节
    (6, 8), (6, 9), (6, 10),                         # 端午
    (9, 15), (9, 16), (9, 17),                       # 中秋
    *{(10, d) for d in range(1, 8)},                 # 国庆
}


def _is_holiday(month: int, day: int) -> int:
    return int((month, day) in HOLIDAYS_2024)


def generate_east_china(days: int = 365, seed: int = 42) -> pd.DataFrame:
    """East China (华东): subtropical, summer AC peak, load 4000-8000 MW.

    Key characteristics:
    - Mild winters (0-15°C), hot humid summers (25-42°C)
    - Air conditioning is the dominant load driver in summer
    - Humidity amplifies AC demand (体感温度)
    - Load peaks in July-August
    """
    np.random.seed(seed)
    hours = days * 24
    timestamps = pd.date_range("2024-01-01", periods=hours, freq="h")

    hour = timestamps.hour
    dow = timestamps.dayofweek
    month = timestamps.month
    doy = timestamps.dayofyear
    day = timestamps.day

    # --- Temperature: subtropical ---
    seasonal_base = 18 + 14 * np.sin((doy - 100) * 2 * np.pi / 365)
    daily_var = 5 * np.sin((hour - 6) * np.pi / 12)
    temperature = seasonal_base + daily_var + np.random.normal(0, 2, hours)
    temperature = np.clip(temperature, -5, 42)

    # --- Humidity: higher in summer ---
    humidity = 65 + 10 * np.sin((doy - 100) * 2 * np.pi / 365) + np.random.normal(0, 8, hours)
    humidity = np.clip(humidity, 30, 95)

    # --- AC index: ramps above 26°C ---
    air_conditioning_index = np.clip((temperature - 26) / 14, 0, 1.0)

    # --- Wind speed: lower in East China (less continental) ---
    wind_base = 2.0 + 0.5 * np.sin((doy - 30) * 2 * np.pi / 365)
    wind_speed = wind_base + np.abs(np.random.normal(0, 1.2, hours))
    wind_speed = np.clip(wind_speed, 0, 12)

    # --- Heating index: mostly 0 in East (mild winters) ---
    heating_index = np.clip((10 - temperature) / 30, 0, 1.0)

    is_weekend = (dow >= 5).astype(int)
    is_holiday = np.array([_is_holiday(int(m), int(d)) for m, d in zip(month, day)])

    # --- Load model ---
    base_load = 5500

    # Daily cycle
    daily = (
        500 * np.sin((hour - 4) * np.pi / 9) * ((hour >= 4) & (hour <= 13))
        + 600 * np.sin((hour - 13) * np.pi / 8) * ((hour >= 13) & (hour <= 21))
        - 400 * ((hour >= 0) & (hour <= 5))
    )

    # Summer AC effect (dominant driver for East China)
    ac_effect = 1800 * air_conditioning_index

    # Mild winter heating (not the dominant effect)
    winter_effect = 200 * np.clip((10 - temperature) / 15, 0, 1)

    # Humidity discomfort boosts AC
    humid_boost = 150 * (humidity / 100) * air_conditioning_index

    # Weekend/holiday reduction
    weekend_effect = -500 * is_weekend - 700 * is_holiday

    noise = np.random.normal(0, 80, hours)
    load = base_load + daily + ac_effect + winter_effect + humid_boost + weekend_effect + noise
    load = np.clip(load, 4000, 8000)

    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature": np.round(temperature, 1),
        "humidity": np.round(humidity, 1),
        "air_conditioning_index": np.round(air_conditioning_index, 3),
        "wind_speed": np.round(wind_speed, 1),
        "heating_index": np.round(heating_index, 3),
        "hour": hour,
        "day_of_week": dow,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "month": month,
        "load_mw": np.round(load, 1),
    })


def generate_north_china(days: int = 365, seed: int = 123) -> pd.DataFrame:
    """North China (华北): continental, winter heating peak, load 5000-9000 MW.

    Key characteristics:
    - Cold winters (-20 to 5°C), hot dry summers (25-38°C)
    - Heating is the dominant load driver in winter
    - Wind speed amplifies heating demand (wind chill)
    - Load peaks in December-February
    """
    np.random.seed(seed)
    hours = days * 24
    timestamps = pd.date_range("2024-01-01", periods=hours, freq="h")

    hour = timestamps.hour
    dow = timestamps.dayofweek
    month = timestamps.month
    doy = timestamps.dayofyear
    day = timestamps.day

    # --- Temperature: continental, much colder winters ---
    seasonal_base = 8 + 18 * np.sin((doy - 100) * 2 * np.pi / 365)
    daily_var = 6 * np.sin((hour - 6) * np.pi / 12)
    temperature = seasonal_base + daily_var + np.random.normal(0, 3, hours)
    temperature = np.clip(temperature, -20, 38)

    # --- Wind speed: higher in North China, windier in spring ---
    wind_base = 3.5 + 1.5 * np.sin((doy - 30) * 2 * np.pi / 365)
    wind_speed = wind_base + np.abs(np.random.normal(0, 2, hours))
    wind_speed = np.clip(wind_speed, 0, 25)

    # --- Heating index: ramps below 10°C ---
    heating_index = np.clip((10 - temperature) / 30, 0, 1.0)

    # --- Humidity: lower in North China (drier continental climate) ---
    humidity = 40 + 8 * np.sin((doy - 100) * 2 * np.pi / 365) + np.random.normal(0, 6, hours)
    humidity = np.clip(humidity, 15, 70)

    # --- AC index: mostly 0 in North (rarely above 26°C) ---
    air_conditioning_index = np.clip((temperature - 26) / 14, 0, 1.0)

    is_weekend = (dow >= 5).astype(int)
    is_holiday = np.array([_is_holiday(int(m), int(d)) for m, d in zip(month, day)])

    # --- Load model ---
    base_load = 6500

    # Daily cycle (sharper morning peak for heating startup)
    daily = (
        700 * np.sin((hour - 4) * np.pi / 8) * ((hour >= 4) & (hour <= 12))
        + 500 * np.sin((hour - 13) * np.pi / 8) * ((hour >= 13) & (hour <= 21))
        - 500 * ((hour >= 0) & (hour <= 5))
    )

    # Winter heating (dominant driver for North China)
    heat_effect = 2200 * heating_index

    # Wind chill amplifies heating demand
    wind_chill = 100 * (wind_speed / 10) * heating_index

    # Summer AC (secondary, less than East)
    summer_ac = 800 * np.clip((temperature - 28) / 10, 0, 1)

    # Weekend/holiday
    weekend_effect = -400 * is_weekend - 600 * is_holiday

    noise = np.random.normal(0, 100, hours)
    load = base_load + daily + heat_effect + wind_chill + summer_ac + weekend_effect + noise
    load = np.clip(load, 5000, 9000)

    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature": np.round(temperature, 1),
        "humidity": np.round(humidity, 1),
        "air_conditioning_index": np.round(air_conditioning_index, 3),
        "wind_speed": np.round(wind_speed, 1),
        "heating_index": np.round(heating_index, 3),
        "hour": hour,
        "day_of_week": dow,
        "is_weekend": is_weekend,
        "is_holiday": is_holiday,
        "month": month,
        "load_mw": np.round(load, 1),
    })


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Generate cross-region load forecast data")
    p.add_argument("--region", choices=["east", "north", "both"], default="both")
    p.add_argument("--output-dir", default=".")
    args = p.parse_args()

    if args.region in ("east", "both"):
        df = generate_east_china()
        path = f"{args.output_dir}/hua_dong_train.csv"
        df.to_csv(path, index=False)
        print(f"华东: {len(df)} rows, load {df['load_mw'].min():.0f}-{df['load_mw'].max():.0f} MW -> {path}")

    if args.region in ("north", "both"):
        df = generate_north_china()
        path = f"{args.output_dir}/hua_bei_train.csv"
        df.to_csv(path, index=False)
        print(f"华北: {len(df)} rows, load {df['load_mw'].min():.0f}-{df['load_mw'].max():.0f} MW -> {path}")
