import google.generativeai as genai
import os

genai.configure(api_key="AIzaSyBSORoWat4GGyVdElQshokyjIzJXXLqi7M")

print("Listing models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
