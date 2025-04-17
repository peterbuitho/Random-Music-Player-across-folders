from setuptools import setup

APP = ['music_player.py']
OPTIONS = {
    'argv_emulation': True,
    'packages': ['PIL', 'vlc', 'mutagen', 'requests'],
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
