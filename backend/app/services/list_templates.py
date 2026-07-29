"""Starter template seed data for the lists module.

The ten packing-era templates (Phase 4, transcribed from
docs/packing-template.md) plus the Phase 6 additions: school supplies,
Christmas gifts, and birthday. Deliberately lean: a helpful head start,
not an overwhelming wall; Maryann edits freely after cloning.

Gift templates seed section scaffolding with almost no items on purpose
— who gets what is hers to fill in ("Emma — Lego set — $40" fits name,
notes, and price with nothing extra).

Pure data, no logic — the seeding itself lives in services/lists.py,
which seeds per kind so new template groups can ship in later phases
without re-touching (or overwriting) the ones she may have edited.
"""

#: (kind, display name, [(section name, [item names]), ...])
TEMPLATES: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "packing",
        "Moving",
        [
            (
                "First-night box",
                [
                    "Toilet paper",
                    "Paper towels",
                    "Phone + chargers",
                    "Medications",
                    "A change of clothes each",
                    "Bedding & pillows",
                    "Snacks & water",
                    "Basic toiletries",
                    "Box cutter",
                ],
            ),
            (
                "Documents & valuables",
                [
                    "IDs & passports",
                    "Birth certificates",
                    "Important financial / legal papers",
                    "Jewelry",
                    "Laptops & drives",
                ],
            ),
            (
                "Kitchen",
                [
                    "Everyday dishes",
                    "Pots & pans",
                    "Utensils",
                    "Coffee maker",
                    "Dish soap",
                ],
            ),
            (
                "Cleaning",
                [
                    "All-purpose cleaner",
                    "Trash bags",
                    "Sponges",
                    "Broom",
                    "Vacuum",
                ],
            ),
            (
                "Tools & hardware",
                [
                    "Screwdrivers",
                    "Drill",
                    "Tape measure",
                    "Furniture hardware (bagged & labeled)",
                    "Picture hooks",
                ],
            ),
            (
                "Packing supplies",
                [
                    "Boxes",
                    "Packing tape",
                    "Bubble wrap",
                    "Markers",
                    "Labels",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Travel",
        [
            (
                "Clothes",
                [
                    "Tops",
                    "Bottoms",
                    "Underwear & socks",
                    "Sleepwear",
                    "Layers / jacket",
                    "Shoes",
                    "Swimwear",
                ],
            ),
            (
                "Toiletries",
                [
                    "Toothbrush & paste",
                    "Deodorant",
                    "Skincare",
                    "Hairbrush",
                    "Razor",
                    "Contacts / glasses",
                ],
            ),
            (
                "Documents & money",
                [
                    "IDs / passports",
                    "Tickets / boarding passes",
                    "Wallet",
                    "Cash",
                    "Insurance info",
                ],
            ),
            (
                "Electronics",
                [
                    "Phone & charger",
                    "Headphones",
                    "Power bank",
                    "Adapters",
                    "Camera",
                ],
            ),
            (
                "Health",
                [
                    "Medications",
                    "Vitamins",
                    "Sunscreen",
                    "Pain reliever",
                    "Band-aids",
                ],
            ),
            (
                "Misc",
                [
                    "Reusable water bottle",
                    "Snacks",
                    "Sunglasses",
                    "Book",
                    "Laundry bag",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Events",
        [
            (
                "Attire",
                [
                    "Outfit",
                    "Shoes",
                    "Accessories",
                    "Backup / change of clothes",
                ],
            ),
            (
                "Grooming",
                [
                    "Deodorant",
                    "Cologne / perfume",
                    "Hair products",
                    "Makeup",
                    "Lint roller",
                ],
            ),
            (
                "Bring",
                [
                    "Gift & card",
                    "Tickets / invitation",
                    "Cash",
                ],
            ),
            (
                "Just in case",
                [
                    "Stain remover",
                    "Safety pins",
                    "Phone charger",
                    "Comfortable shoes",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Work",
        [
            (
                "Tech",
                [
                    "Laptop & charger",
                    "Phone & charger",
                    "Mouse",
                    "Adapters",
                    "Notebook & pen",
                ],
            ),
            (
                "Documents",
                [
                    "Presentation materials",
                    "Business cards",
                    "ID / badge",
                    "Travel itinerary",
                ],
            ),
            (
                "Attire",
                [
                    "Work outfits",
                    "Dress shoes",
                    "Accessories",
                ],
            ),
            (
                "Essentials",
                [
                    "Medications",
                    "Water bottle",
                    "Snacks",
                    "Headphones",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Outdoor Activities",
        [
            (
                "Shelter & sleep",
                [
                    "Tent",
                    "Sleeping bag",
                    "Sleeping pad",
                    "Pillow",
                    "Tarp",
                ],
            ),
            (
                "Cooking",
                [
                    "Stove & fuel",
                    "Cookware",
                    "Utensils",
                    "Lighter / matches",
                    "Cooler",
                ],
            ),
            (
                "Clothing",
                [
                    "Layers",
                    "Rain jacket",
                    "Hat",
                    "Hiking boots",
                    "Extra socks",
                ],
            ),
            (
                "Navigation & safety",
                [
                    "Map / GPS",
                    "Headlamp",
                    "First-aid kit",
                    "Multi-tool",
                    "Whistle",
                ],
            ),
            (
                "Food & water",
                [
                    "Water bottles / filter",
                    "Meals",
                    "Snacks",
                ],
            ),
            (
                "Personal",
                [
                    "Sunscreen",
                    "Bug spray",
                    "Toiletries",
                    "Trash bags",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Family and Kids",
        [
            (
                "Diapering",
                [
                    "Diapers",
                    "Wipes",
                    "Changing pad",
                    "Diaper cream",
                    "Extra outfit",
                ],
            ),
            (
                "Feeding",
                [
                    "Bottles / formula",
                    "Snacks",
                    "Sippy cups",
                    "Bibs",
                    "Utensils",
                ],
            ),
            (
                "Clothing",
                [
                    "Outfits",
                    "Pajamas",
                    "Socks",
                    "Jacket",
                    "Hat",
                ],
            ),
            (
                "Comfort & fun",
                [
                    "Favorite toy",
                    "Blanket",
                    "Pacifier",
                    "Books",
                    "Tablet",
                ],
            ),
            (
                "Health",
                [
                    "Children's medications",
                    "Thermometer",
                    "Band-aids",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Emergency Preparedness",
        [
            (
                "Water & food",
                [
                    "Bottled water",
                    "Non-perishable food",
                    "Manual can opener",
                ],
            ),
            (
                "First aid",
                [
                    "First-aid kit",
                    "Medications",
                    "Prescriptions",
                ],
            ),
            (
                "Tools & light",
                [
                    "Flashlight",
                    "Batteries",
                    "Multi-tool",
                    "Whistle",
                    "Duct tape",
                ],
            ),
            (
                "Documents",
                [
                    "ID copies",
                    "Insurance info",
                    "Cash",
                    "Emergency contacts",
                ],
            ),
            (
                "Communication",
                [
                    "Phone charger / power bank",
                    "Battery or hand-crank radio",
                ],
            ),
            (
                "Warmth",
                [
                    "Emergency blanket",
                    "Extra clothing",
                    "Rain poncho",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Shipping and Storage",
        [
            (
                "Materials",
                [
                    "Boxes",
                    "Packing tape",
                    "Bubble wrap",
                    "Packing paper",
                    "Stretch wrap",
                ],
            ),
            (
                "Protection",
                [
                    "Furniture blankets",
                    "Corner protectors",
                    "Mattress bags",
                    "Silica packs (for long storage)",
                ],
            ),
            (
                "Labeling & inventory",
                [
                    "Markers",
                    "Labels",
                    "Inventory list",
                    "Fragile stickers",
                ],
            ),
            (
                "Tools",
                [
                    "Box cutter",
                    "Scissors",
                    "Tape gun",
                ],
            ),
        ],
    ),
    (
        "packing",
        "Everyday Bags and Kits",
        [
            (
                "Purse / everyday carry",
                [
                    "Wallet",
                    "Keys",
                    "Phone",
                    "Lip balm",
                    "Hand sanitizer",
                    "Gum / mints",
                    "Pen",
                ],
            ),
            (
                "Diaper bag (on the go)",
                [
                    "Diapers",
                    "Wipes",
                    "Changing pad",
                    "Snack",
                    "Extra outfit",
                ],
            ),
            (
                "Car kit",
                [
                    "Phone charger",
                    "Umbrella",
                    "Reusable bags",
                    "Tissues",
                    "First-aid basics",
                ],
            ),
            (
                "Emergency car kit",
                [
                    "Jumper cables",
                    "Flashlight",
                    "Blanket",
                    "Water",
                    "Ice scraper",
                ],
            ),
        ],
    ),
    # Custom: no seeded items — starts with one empty "Items" section so
    # she builds her own from a blank (but not zero-structure) slate.
    # A single section also renders headerless, so it reads as a plain
    # flat list — the shape of a one-off to-do list.
    (
        "custom",
        "Custom",
        [
            ("Items", []),
        ],
    ),
    # ---- Phase 6 additions ----
    (
        "shopping",
        "School Supplies",
        [
            (
                "Gear",
                [
                    "Backpack",
                    "Lunch box",
                    "Water bottle",
                    "Sneakers",
                ],
            ),
            (
                "Supplies",
                [
                    "Pencils",
                    "Erasers",
                    "Crayons / markers",
                    "Glue sticks",
                    "Notebooks",
                    "Folders",
                    "Scissors",
                    "Pencil case",
                    "Highlighters",
                    "Tissues (for the classroom)",
                ],
            ),
        ],
    ),
    (
        "shopping",
        "Christmas Gifts",
        [
            ("Family", []),
            ("Friends", []),
            ("Teachers & neighbors", []),
            ("Stocking stuffers", []),
            (
                "Wrapping",
                [
                    "Wrapping paper",
                    "Tape",
                    "Gift tags",
                    "Bows & ribbon",
                ],
            ),
        ],
    ),
    (
        "shopping",
        "Birthday",
        [
            ("Gifts", []),
            (
                "Party",
                [
                    "Cake",
                    "Candles",
                    "Balloons",
                    "Decorations",
                    "Paper plates & cups",
                    "Party favors",
                    "Invitations",
                ],
            ),
        ],
    ),
]
