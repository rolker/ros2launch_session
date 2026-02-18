from setuptools import find_packages, setup

package_name = 'ros2launch_session'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Roland Arsenault',
    maintainer_email='roland@ccom.unh.edu',
    description='Managed ROS 2 launch sessions for reliable startup, monitoring, and shutdown',
    license='Apache-2.0',
    tests_require=['pytest'],
)
