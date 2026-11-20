def demo_rows() -> list[dict]:
    """Synthetic morning-shift measurements for one drawing revision."""
    setups = [
        ("MJ-17", "IM-03", 42, 224, 15, -0.12, -0.02, 8),
        ("MJ-22", "IM-07", 53, 233, 17, 0.02, 0.01, 8),
        ("MJ-31", "IM-11", 64, 241, 19, 0.16, 0.04, 8),
        ("MJ-44", "IM-05", 52, 230, 16, 0.00, 0.00, 4),
    ]
    width_offset = (0.04, 0.03, 0.03, 0.02, 0.00, 0.01, -0.02, -0.03)
    height_offset = (-0.03, -0.02, -0.01, -0.01, 0.00, 0.01, 0.02, 0.02)
    rows = []
    for die, machine, pressure, melt, cooling, width, height, count in setups:
        for index in range(count):
            resin_lot = "ABS-261118A" if index % 2 == 0 else "ABS-261118B"
            rows.append({
                "sample_id": f"K261118-{machine[-2:]}-{index + 1:02d}",
                "measured_on": "2026-11-18",
                "die": die,
                "machine": machine,
                "resin_lot": resin_lot,
                "hold_pressure_mpa": float(pressure + 2 * (index // 2)),
                "melt_temp_c": float(melt if machine == "IM-07" else melt + index // 4),
                "cooling_seconds": cooling + 0.5 * (index % 3),
                "width_deviation_mm": round(width + width_offset[index], 2),
                "height_deviation_mm": round(height + height_offset[index], 2),
            })
    return rows
