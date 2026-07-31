import sys, os
# backend dir, relative to this file — survives any folder rename/move
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.card_template_service import composite_card
from database import db

with db() as conn:
    heroes = conn.execute('SELECT id, name, portrait_path, birth_star, hero_class FROM heroes').fetchall()

count = 0
for h in heroes:
    try:
        composite_card(h['id'], h['portrait_path'], h['birth_star'], h['name'], crop_face=False, hero_class=h['hero_class'])
        composite_card(h['id'], h['portrait_path'], h['birth_star'], h['name'], crop_face=True, hero_class=h['hero_class'])
        count += 1
        print(f"OK: {h['name']} ({h['hero_class']})")
    except Exception as e:
        print(f"ERR: {h['name']} - {e}")

print(f"Done! {count} heroes processed.")
