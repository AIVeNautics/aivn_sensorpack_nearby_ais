from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = PathJoinSubstitution([
        FindPackageShare("aivn_sensorpack_nearby_ais"),
        "config",
        "nearby_ais.yaml",
    ])

    return LaunchDescription([
        Node(
            package="aivn_sensorpack_nearby_ais",
            executable="nearby_ais_node",
            name="nearby_ais_node",
            output="screen",
            parameters=[config_file],
        ),
    ])
