from PIL import Image

# Open the PNG file
img = Image.open('favicon_256.png')

# Convert to ICO (include common icon sizes)
img.save('favicon.ico', format='ICO', sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])
print('favicon.ico created.')
