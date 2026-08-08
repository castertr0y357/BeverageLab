import sys

with open('soda_mixer/flavors/views/coffee_chemistry.py', 'r') as f:
    lines = f.readlines()

new_lines = []
new_lines.extend(lines[:11])
new_lines.append('from ..engines.base import BaseChemistryEngine\n')
new_lines.append('\n')
new_lines.append('class CoffeeChemistryEngine(BaseChemistryEngine):\n')
new_lines.append('    def __init__(self, ingredients_input, drink_category, cup_size_oz, espresso_hot_mode):\n')
new_lines.append('        super().__init__(ingredients_input)\n')
new_lines.append('        self.drink_category = drink_category\n')
new_lines.append('        self.cup_size_oz = cup_size_oz\n')
new_lines.append('        self.espresso_hot_mode = espresso_hot_mode\n')
new_lines.append('\n')
new_lines.append('    def process(self):\n')
new_lines.append('        drink_category = self.drink_category\n')
new_lines.append('        cup_size_oz = self.cup_size_oz\n')
new_lines.append('        ingredients_input = self.ingredients_input\n')
new_lines.append('        espresso_hot_mode = self.espresso_hot_mode\n')

# skip lines up to drink_cat_lower
start_idx = 28
for line in lines[start_idx:673]:
    if line == '\n':
        new_lines.append('\n')
    else:
        new_lines.append('    ' + line)

new_lines.append('\n')
new_lines.append('@csrf_exempt\n')
new_lines.append('@require_http_methods([\"POST\"])\n')
new_lines.append('def coffee_chemistry_api(request):\n')
new_lines.append('    import json\n')
new_lines.append('    try:\n')
new_lines.append('        data = json.loads(request.body)\n')
new_lines.append('    except json.JSONDecodeError as e:\n')
new_lines.append('        logger.warning(f\"CoffeeChemistry - Warning - Invalid JSON payload: {e}\")\n')
new_lines.append('        return JsonResponse({\"error\": \"Invalid JSON\"}, status=400)\n')
new_lines.append('\n')
new_lines.append('    drink_category = data.get(\"drink_category\", \"Hot Coffee\").strip()\n')
new_lines.append('    cup_size_oz = float(data.get(\"cup_size_oz\", 12.0))\n')
new_lines.append('    ingredients_input = data.get(\"ingredients\", [])\n')
new_lines.append('    espresso_hot_mode = data.get(\"espresso_hot_mode\", \"shots\").strip().lower()\n')
new_lines.append('\n')
new_lines.append('    engine = CoffeeChemistryEngine(ingredients_input, drink_category, cup_size_oz, espresso_hot_mode)\n')
new_lines.append('    return JsonResponse(engine.process())\n')

with open('soda_mixer/flavors/views/coffee_chemistry.py', 'w') as f:
    f.writelines(new_lines)
