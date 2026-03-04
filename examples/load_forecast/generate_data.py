"""Generate synthetic hourly load data for load forecasting demonstration."""

import numpy as np
import pandas as pd


def generate_load_data(days: int = 365, seed: int = 42) -> pd.DataFrame:
    """Generate 1 year of hourly synthetic load data.

    Patterns included:
    - Daily cycle (peak at 10am and 7pm, trough at 3am)
    - Weekly pattern (weekday vs weekend)
    - Seasonal pattern (summer/winter peaks, spring/autumn valleys)
    - Temperature correlation (quadratic: AC in summer, heating in winter)
    - Random noise
    """
    np.random.seed(seed)
    hours = days * 24
    timestamps = pd.date_range("2024-01-01", periods=hours, freq="h")

    hour = timestamps.hour
    day_of_week = timestamps.dayofweek
    month = timestamps.month
    day_of_year = timestamps.dayofyear

    # Temperature: seasonal base + daily variation + noise
    seasonal_temp = 15 + 15 * np.sin((day_of_year - 100) * 2 * np.pi / 365)
    daily_temp_var = 5 * np.sin((hour - 6) * np.pi / 12)
    temperature = seasonal_temp + daily_temp_var + np.random.normal(0, 2, hours)

    # Humidity: inversely correlated with temperature + noise
    humidity = 70 - 0.5 * (temperature - 15) + np.random.normal(0, 5, hours)
    humidity = np.clip(humidity, 20, 95)

    is_weekend = (day_of_week >= 5).astype(int)

    # Load composition
    base_load = 5000  # MW

    # Daily pattern: morning peak + evening peak
    daily_pattern = (
        600 * np.sin((hour - 4) * np.pi / 9) * (hour >= 4) * (hour <= 13)  # morning ramp
        + 500 * np.sin((hour - 13) * np.pi / 8) * (hour >= 13) * (hour <= 21)  # evening peak
        - 300 * ((hour >= 0) & (hour <= 5))  # night valley
    )

    # Temperature effect: U-shaped (AC when hot, heating when cold)
    comfort_temp = 20
    temp_effect = 30 * (temperature - comfort_temp) ** 2 / 10

    # Seasonal base variation
    seasonal_load = 300 * np.sin((month - 3) * np.pi / 6)

    # Weekend reduction
    weekend_effect = -600 * is_weekend

    # Random noise
    noise = np.random.normal(0, 100, hours)

    load = base_load + daily_pattern + temp_effect + seasonal_load + weekend_effect + noise
    load = np.maximum(load, 2500)  # floor

    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature": np.round(temperature, 1),
        "humidity": np.round(humidity, 1),
        "hour": hour,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "month": month,
        "load_mw": np.round(load, 1),
    })


if __name__ == "__main__":
    df = generate_load_data()
    print(f"Generated {len(df)} hourly records")
    print(f"Date range: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    print(f"Load range: {df['load_mw'].min():.0f} ~ {df['load_mw'].max():.0f} MW")
    print(f"\nSample:\n{df.head(10)}")
    df.to_csv("load_data.csv", index=False)
    print("\nSaved to load_data.csv")
