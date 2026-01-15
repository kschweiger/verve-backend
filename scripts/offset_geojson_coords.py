import json
import random
import sys
from pathlib import Path


def offset_coords(file_name: str, output_prefix: str = "processed_") -> None:
    """
    Process a GeoJSON or Verve JSON file to:
    1. Truncate coordinates/heartRates/coordTimes to 100 points
    2. Offset lat/lon by random amounts to obscure location (50-100km)
    3. Save to a new file with prefix
    """
    # Read the JSON file
    file_path = Path(file_name)
    with open(file_path, "r") as f:
        data = json.load(f)

    # Generate random offsets (0.45-0.9 degrees, ~50-100km)
    # Sign is also random to make it unpredictable
    lat_offset = random.uniform(0.45, 0.9) * random.choice([-1, 1])
    lon_offset = random.uniform(0.45, 0.9) * random.choice([-1, 1])

    total_points = 0

    # Process each feature
    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        properties = feature.get("properties", {})

        # Check if geometry exists and has coordinates
        if geometry and geometry.get("coordinates"):
            coordinates = geometry["coordinates"]
            total_points = len(coordinates)

            # Truncate to 100 points and apply offset
            new_coords = []
            for i in range(min(100, total_points)):
                lon, lat, *rest = coordinates[i]
                new_coords.append([lon + lon_offset, lat + lat_offset] + rest)

            # Update geometry
            geometry["coordinates"] = new_coords
        else:
            # No geometry, just get count from heartRates or coordTimes
            total_points = len(
                properties.get("heartRates", properties.get("coordTimes", []))
            )

        # Truncate heart rates and times to match
        if "heartRates" in properties:
            properties["heartRates"] = properties["heartRates"][:100]

        if "coordTimes" in properties:
            properties["coordTimes"] = properties["coordTimes"][:100]

    # Create output path with prefix
    output_path = file_path.parent / f"{output_prefix}{file_path.name}"

    # Write to new file
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Processed {file_path}")
    print(f"  Reduced from {total_points} to {min(100, total_points)} points")
    if any(
        f.get("geometry") and f["geometry"].get("coordinates")
        for f in data.get("features", [])
    ):
        print(f"  Applied random offset: lat={lat_offset:.6f}°, lon={lon_offset:.6f}°")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    file_name = sys.argv[1]
    offset_coords(file_name)
