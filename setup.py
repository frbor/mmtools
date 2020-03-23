"""status bar for mattermost"""

from os import path

from setuptools import setup

# read the contents of your README file
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), "rb") as f:
    long_description = f.read().decode('utf-8')

setup(
    name="mmtools",
    version="0.0.6",
    author="Fredrik Borg",
    zip_safe=True,
    author_email="fredrikb.borg@gmail.com",
    description="mmtools",
    long_description=long_description,
    long_description_content_type='text/markdown',
    license="ISC",
    packages=["mmtools"],
    url="https://github.com/frbor/mmtools",
    entry_points={
        'console_scripts': [
            'mmstatus = mmtools.status:main',
            'mmwatch = mmtools.watch:main',
            'mmconfig= mmtools.config:main',
        ]
    },
    python_requires='>=3.6, <4',
    install_requires=[
        'caep',
        'pydantic',
        'mattermostdriver',
        'passpy',
        'notify2',
        'dbus-python',
        'requests'
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "License :: OSI Approved :: ISC License (ISCL)",
    ],
)
