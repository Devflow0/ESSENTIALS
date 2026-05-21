import streamlit as st
import os
import base64

def get_svg_content(icon_name):
    """Reads SVG content from the assets folder."""
    icon_path = os.path.join("assets", "images", "icons", f"{icon_name}.svg")
    if not os.path.exists(icon_path):
        # Try without extension if it was passed with one
        icon_path = os.path.join("assets", "images", "icons", icon_name)
        if not os.path.exists(icon_path):
            return None
    
    with open(icon_path, "r", encoding="utf-8") as f:
        return f.read()

def render_icon(icon_name, color="currentColor", size=20, margin="0 8px 0 0"):
    """Returns an inline SVG string styled for use in HTML."""
    svg_content = get_svg_content(icon_name)
    if not svg_content:
        return ""
    
    # Inject style into the <svg> tag
    style = f'width: {size}px; height: {size}px; vertical-align: middle; color: {color}; margin: {margin}; fill: none; stroke: {color}; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;'
    
    # Remove existing width/height/style if present and inject our own
    import re
    svg_content = re.sub(r'<svg\s+', f'<svg style="{style}" ', svg_content)
    # Ensure it uses currentColor or the specified color if it had hardcoded colors
    # svg_content = svg_content.replace('stroke="currentColor"', f'stroke="{color}"')
    
    return svg_content

def get_icon_base64(icon_name):
    """Returns base64 encoded SVG for CSS usage."""
    svg_content = get_svg_content(icon_name)
    if not svg_content:
        return ""
    return base64.b64encode(svg_content.encode()).decode()

def icon_header(text, icon_name, size=32, color="#1a1a2e"):
    """Renders a header with an icon."""
    icon_svg = render_icon(icon_name, color=color, size=size)
    st.markdown(f'<div style="display: flex; align-items: center; margin-bottom: 1rem;">{icon_svg}<h1 style="margin: 0; font-size: {size*0.8}px; color: {color};">{text}</h1></div>', unsafe_allow_html=True)

def icon_subheader(text, icon_name, size=24, color="#334155"):
    """Renders a subheader with an icon."""
    icon_svg = render_icon(icon_name, color=color, size=size)
    st.markdown(f'<div style="display: flex; align-items: center; margin: 1.5rem 0 1rem 0;">{icon_svg}<h2 style="margin: 0; font-size: {size*0.8}px; color: {color};">{text}</h2></div>', unsafe_allow_html=True)
