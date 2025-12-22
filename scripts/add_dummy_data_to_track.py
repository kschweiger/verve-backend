import datetime
import random

from geo_track_analyzer import GPXFileTrack


def main(file_name: str, avg_target_speed_kmh: float) -> None:
    track = GPXFileTrack(file_name)
    print(track)

    points = track.track.segments[0].points
    print(points[0:10])

    # Set start time for the first point
    start_time = datetime.datetime.now(datetime.timezone.utc)
    points[0].time = start_time

    # Calculate time for each subsequent point based on distance and speed
    for i in range(1, len(points)):
        prev_point = points[i - 1]
        curr_point = points[i]

        # Calculate distance between points in meters
        distance = prev_point.distance_3d(curr_point)
        if distance is None:
            distance = prev_point.distance_2d(curr_point)

        if distance and prev_point.time:
            # Add randomness: vary speed by ±20%
            speed_variation = random.uniform(0.8, 1.2)
            actual_speed_kmh = avg_target_speed_kmh * speed_variation

            # Convert speed to m/s
            speed_ms = actual_speed_kmh * 1000 / 3600

            # Calculate time delta
            time_delta_seconds = distance / speed_ms

            # Set current point time
            curr_point.time = prev_point.time + datetime.timedelta(
                seconds=time_delta_seconds
            )

    # Save the modified GPX file
    output_file = file_name.replace(".gpx", "_with_times.gpx")
    with open(output_file, "w") as f:
        f.write(track.get_xml())

    print(f"Modified GPX saved to: {output_file}")
    print(f"Start time: {points[0].time}")
    print(f"End time: {points[-1].time}")
    if points[0].time and points[-1].time:
        duration = points[-1].time - points[0].time
        print(f"Total duration: {duration}")

    track.plot(kind="profile", include_velocity=True).show()


if __name__ == "__main__":
    file_name = "scripts/Bédoin - 21,2 km, 1.585 hm.gpx"
    main(file_name, 10)
