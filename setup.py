from glob import glob
import os

from setuptools import find_packages, setup


package_name = "aivn_sensorpack_nearby_ais"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    install_requires=["setuptools"],
    zip_safe=True,
    author="jaewonpark",
    author_email="jaewon.park@aivenautics.com",
    description="Unified AIS and ECS nearby ship serial receiver.",
    license="Apache-2.0",
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    entry_points={
        "console_scripts": [
            "nearby_ais_node = aivn_sensorpack_nearby_ais.nearby_ais_node:main",
        ],
    },
)
