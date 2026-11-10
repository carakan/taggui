"""Prompt templates used when asking the local vision LLM for tags.

The templates are kept verbatim from the original `lora_tagger.py` script so
that the tagging behaviour stays identical between the script and the GUI.
`{trigger}` is the trigger word of the dataset and `{max_tags}` the maximum
number of tags the model is allowed to return.
"""

TAG_PROMPT_TEMPLATE = """You are tagging an image for LoRA training of image generation models (SD1.5, SDXL, Z-Image). The trigger word "{trigger}" is added to the caption separately.

Rules:
- Output ONLY the comma-separated tag list. No explanations, do not restate these rules.
- Lowercase, single spaces (no underscores), ordered from most to least important.
- Telegraphic danbooru style: no articles (a/the), no verbs, no full sentences. Use canonical danbooru terms where they exist ("looking at viewer", "full body", "standing") and always pick the most standard/common wording — the same concept must get the exact same tag across the whole dataset.
- Describe only what is clearly visible: subjects (count, gender, appearance, distinctive identity traits), clothing with materials, patterns and dominant colors, accessories, pose, action and interaction with surroundings, key objects and their spatial relations, framing, setting, lighting.
- Each tag must add distinct information — no near-duplicates.
- COLOR RULE (mandatory): tag the colors of every main garment (dress, skirt, vest, poncho, shawl, hat...). One color: "red dress". Two or more colors on the same garment: exactly ONE tag with ALL its colors hyphenated in ALPHABETICAL order before the garment word — "black-red dress", "black-red-white dress", "green-yellow skirt". Include trim/embroidery colors, keep the order strictly alphabetical, never split the colors into separate tags. NEVER output a bare color group with no garment word (not "black-red", not "red-white") — colors exist only inside a full tag like "black-red dress".
- Prefer specific multi-word tags over generic single-word ones. One-word tags only when highly specific, like petticoat or sequins; never generic filler words such as photo, dance or hat. A shorter precise list is better than a full vague one.
- NEVER output quality, style or meta tags (best quality, masterpiece, high resolution, 4k, award winning, photorealistic...), and no media/self-reference tags (photo, photograph, image, picture, footage, watermark, text).
- Do NOT tag the overall concept that the trigger "{trigger}" represents (e.g. the dance, festival or character name/type) — the trigger covers it. DO tag its visible components: garments, props, attributes, pose, setting details.
- Category limits: people/count/skin/hair up to 6 tags; clothing and accessories up to 12; pose, expression and framing up to 6; setting, background and lighting up to 5; mood, event and context up to 3 TOTAL.
- Focus ~70% of the tags on the main subject(s): appearance, clothing, pose, action, distinctive traits. Setting, background and lighting together: ~30% or less — only what clearly matters.
- People/animal/subject count: exactly ONE danbooru-style count tag for the main living subjects (e.g. 1girl, 2girls, 1boy). Never count using other words (woman, man, child, people...) and never output more than one count tag.
- NEVER count objects, clothing, or accessories. Tags are singular concepts — quantity is implied (e.g. "shoes", not "2 shoes"; "buttons", not "3 buttons").
- NEVER output a number glued to a word with no space (e.g. 1fan, 2hats, 1dress). Count tags exist ONLY for people/animals/subject (1girl, 2boys).
- Do NOT guess hidden details, do NOT transcribe text or watermarks, do NOT invent things not visible in the image.
- Do NOT invent nationality, ethnicity or cultural-origin labels (e.g. spanish-dance, latin festival, mexican dress) — origin is not something you can see.
- Aim for 12-20 well-chosen tags; never pad to reach the limit. At most {max_tags} tags."""

BASETAG_HINT = """
- Concept-specific tags for this dataset — check the image for each of them and include ONLY the ones clearly visible, using these exact words: {basetags}
- Do NOT include a tag from this list if it is not clearly present in the photo. When in doubt, leave it out — never force list tags into the output."""

ANCHOR_HINT = """
- Already verified for this image — treat as ground-truth context, do not contradict them: {anchors}"""

PRESERVE_HINT = """
- Dataset-local vocabulary — cultural/proper terms you may not recognize (dance names, local garment names, Spanish words). For each one clearly visible in the photo, include it using these EXACT words — never rename or translate them: {preserve}
- When in doubt, leave it out — never force list terms into the output."""


def build_prompt(trigger: str, max_tags: int, template: str | None = None,
                 basetags: list[str] | None = None,
                 anchors: list[str] | None = None,
                 preserve: list[str] | None = None,
                 prune: bool = False) -> str:
    """Build the full prompt sent to the model.

    A fresh copy of the template is used for every image; the optional hint
    blocks are appended to it (never a second prompt). In prune mode the
    anchors are skipped, because the whole caption is rebuilt from the image.
    """
    template = TAG_PROMPT_TEMPLATE if template is None else template
    basetags = basetags or []
    anchors = anchors or []
    preserve = preserve or []
    prompt = template.format(trigger=trigger, max_tags=max_tags)
    if anchors and not prune:
        prompt += ANCHOR_HINT.format(anchors=', '.join(anchors))
    if basetags:
        prompt += BASETAG_HINT.format(basetags=', '.join(basetags))
    if prune and preserve:
        prompt += PRESERVE_HINT.format(preserve=', '.join(preserve))
    return prompt
