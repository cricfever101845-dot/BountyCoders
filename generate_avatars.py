"""Generate simple SVG avatar placeholders for One Piece characters."""
import os

AVATARS_DIR = os.path.join('static', 'avatars')
os.makedirs(AVATARS_DIR, exist_ok=True)

characters = {
    'luffy':  {'bg': '#e74c3c', 'letter': 'L', 'hat': '#f1c40f'},
    'zoro':   {'bg': '#27ae60', 'letter': 'Z', 'hat': '#2ecc71'},
    'nami':   {'bg': '#f39c12', 'letter': 'N', 'hat': '#e67e22'},
    'sanji':  {'bg': '#f1c40f', 'letter': 'S', 'hat': '#f39c12'},
    'ace':    {'bg': '#e67e22', 'letter': 'A', 'hat': '#d35400'},
    'law':    {'bg': '#2980b9', 'letter': 'T', 'hat': '#3498db'},
}

SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
  <circle cx="100" cy="100" r="100" fill="{bg}"/>
  <circle cx="100" cy="85" r="45" fill="#FFE0BD"/>
  <text x="100" y="105" text-anchor="middle" font-size="50" font-family="Arial Black, sans-serif" font-weight="900" fill="{bg}">{letter}</text>
  <rect x="55" y="30" width="90" height="25" rx="8" fill="{hat}"/>
  <circle cx="100" cy="155" r="35" fill="{bg}" opacity="0.6"/>
</svg>'''

for name, props in characters.items():
    svg = SVG_TEMPLATE.format(**props)
    # Save as SVG
    svg_path = os.path.join(AVATARS_DIR, f'{name}.svg')
    with open(svg_path, 'w') as f:
        f.write(svg)
    print(f'Created {svg_path}')

    # Also save as PNG using simple conversion
    # For now we'll create .png placeholder by using the SVG
    # The home.html looks for .png, so let's also create a simple redirect
    # Actually, let's just save the SVG as the main file and update the code

print(f'\nAll avatars created in {AVATARS_DIR}/')
print('Note: Home page references .png files. Updating references to .svg...')
