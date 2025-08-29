"""
Run this script to create a simple icon.png for QGIS Copilot
Requires PIL/Pillow: pip install Pillow
"""

try:
    from PIL import Image, ImageDraw
    
    # Create a 24x24 icon
    size = (24, 24)
    icon = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    
    # Draw QGIS Copilot icon - chat bubble with AI elements
    # Main chat bubble background
    draw.rounded_rectangle([1, 1, 19, 15], radius=4, fill=(52, 152, 219, 255))
    
    # Triangle for speech bubble tail
    draw.polygon([(5, 15), (9, 19), (13, 15)], fill=(52, 152, 219, 255))
    
    # AI indicator - central dot with connection lines
    draw.ellipse([10, 7, 12, 9], fill=(255, 255, 255, 255))  # Center dot
    draw.line([(6, 8), (10, 8)], fill=(255, 255, 255, 255), width=1)  # Left line
    draw.line([(12, 8), (16, 8)], fill=(255, 255, 255, 255), width=1)  # Right line
    draw.line([(11, 5), (11, 7)], fill=(255, 255, 255, 255), width=1)  # Top line
    draw.line([(11, 9), (11, 11)], fill=(255, 255, 255, 255), width=1)  # Bottom line
    
    # Small dots at line ends
    draw.ellipse([5, 7, 7, 9], fill=(255, 255, 255, 255))
    draw.ellipse([15, 7, 17, 9], fill=(255, 255, 255, 255))
    draw.ellipse([10, 4, 12, 6], fill=(255, 255, 255, 255))
    draw.ellipse([10, 10, 12, 12], fill=(255, 255, 255, 255))
    
    # Save icon
    icon.save('icon.png')
    print("✓ QGIS Copilot icon created successfully: icon.png")
    
except ImportError:
    print("PIL/Pillow not available.")
    print("Either install it with: pip install Pillow")
    print("Or create a 24x24 PNG icon manually and name it 'icon.png'")
except Exception as e:
    print(f"Error creating icon: {e}")
    print("Create a 24x24 PNG icon manually and name it 'icon.png'")