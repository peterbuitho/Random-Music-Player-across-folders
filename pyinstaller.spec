# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(['music_player.py'],
             pathex=['.'],
             binaries=[],
             datas=[],
             hiddenimports=['PIL', 'vlc', 'mutagen', 'requests'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='music_player',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False, icon='music_note_icon.ico')
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='music_player',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False, icon='music_note_icon.ico',
          singlefile=True)
