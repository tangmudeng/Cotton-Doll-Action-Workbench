from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "generated_spine" / "cotton_doll_runtime_draft.json"

BONES = [
    {"name": "root"},
    {"name": "view_root", "parent": "root"},
    {"name": "pelvis", "parent": "view_root", "length": 90},
    {"name": "spine_01", "parent": "pelvis", "length": 70},
    {"name": "spine_02", "parent": "spine_01", "length": 70},
    {"name": "chest", "parent": "spine_02", "length": 90},
    {"name": "neck", "parent": "chest", "length": 28},
    {"name": "head", "parent": "neck", "length": 80},
    {"name": "clavicle_l", "parent": "chest", "length": 22},
    {"name": "upper_arm_l", "parent": "clavicle_l", "length": 58},
    {"name": "lower_arm_l", "parent": "upper_arm_l", "length": 48},
    {"name": "hand_l", "parent": "lower_arm_l", "length": 22},
    {"name": "clavicle_r", "parent": "chest", "length": 22},
    {"name": "upper_arm_r", "parent": "clavicle_r", "length": 58},
    {"name": "lower_arm_r", "parent": "upper_arm_r", "length": 48},
    {"name": "hand_r", "parent": "lower_arm_r", "length": 22},
    {"name": "thigh_l", "parent": "pelvis", "length": 72},
    {"name": "calf_l", "parent": "thigh_l", "length": 64},
    {"name": "foot_l", "parent": "calf_l", "length": 26},
    {"name": "thigh_r", "parent": "pelvis", "length": 72},
    {"name": "calf_r", "parent": "thigh_r", "length": 64},
    {"name": "foot_r", "parent": "calf_r", "length": 26},
]

SLOTS = [
    ("slot_hair_back", "head", "hair_back_base"),
    ("slot_leg_l", "thigh_l", "leg_l_base"),
    ("slot_leg_r", "thigh_r", "leg_r_base"),
    ("slot_body", "pelvis", "body_base"),
    ("slot_arm_l_back", "upper_arm_l", "arm_upper_l_base"),
    ("slot_arm_r_back", "upper_arm_r", "arm_upper_r_base"),
    ("slot_head", "head", "head_base"),
    ("slot_face", "head", "eye_open"),
    ("slot_arm_l_front", "lower_arm_l", "lower_arm_l_base"),
    ("slot_arm_r_front", "lower_arm_r", "lower_arm_r_base"),
    ("slot_hair_front", "head", "hair_front_base"),
    ("slot_hand_l", "hand_l", "hand_l_base"),
    ("slot_hand_r", "hand_r", "hand_r_base"),
    ("slot_accessory", "head", "accessory_none"),
]

ATTACHMENTS = {
    "hair_back_base": {"type": "region", "path": "placeholder/hair_back_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "leg_l_base": {"type": "region", "path": "placeholder/leg_l_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "leg_r_base": {"type": "region", "path": "placeholder/leg_r_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "body_base": {"type": "region", "path": "placeholder/body_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "arm_upper_l_base": {"type": "region", "path": "placeholder/arm_upper_l_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "arm_upper_r_base": {"type": "region", "path": "placeholder/arm_upper_r_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "head_base": {"type": "region", "path": "placeholder/head_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "eye_open": {"type": "region", "path": "placeholder/eye_open", "x": 0, "y": 0, "width": 1, "height": 1},
    "lower_arm_l_base": {"type": "region", "path": "placeholder/lower_arm_l_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "lower_arm_r_base": {"type": "region", "path": "placeholder/lower_arm_r_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "hair_front_base": {"type": "region", "path": "placeholder/hair_front_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "hand_l_base": {"type": "region", "path": "placeholder/hand_l_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "hand_r_base": {"type": "region", "path": "placeholder/hand_r_base", "x": 0, "y": 0, "width": 1, "height": 1},
    "accessory_none": {"type": "region", "path": "placeholder/accessory_none", "x": 0, "y": 0, "width": 1, "height": 1},
}


def rotate_keys(names: list[str], values: list[float]):
    return [{"value": values[0]}, {"time": 0.4, "value": values[1]}, {"time": 0.8, "value": values[0]}]


def main() -> None:
    attachments = {slot: {attachment: ATTACHMENTS[attachment]} for slot, _, attachment in SLOTS}
    idle_bones = {
        "chest": {"rotate": rotate_keys(["chest"], [0, 1.5])},
        "head": {"rotate": rotate_keys(["head"], [0, -1.0])},
        "upper_arm_l": {"rotate": rotate_keys(["upper_arm_l"], [0, -2.5])},
        "upper_arm_r": {"rotate": rotate_keys(["upper_arm_r"], [0, 2.5])},
    }
    walk_bones = {
        "thigh_l": {"rotate": [{"value": 8}, {"time": 0.2, "value": -12}, {"time": 0.4, "value": 8}, {"time": 0.8, "value": 8}]},
        "thigh_r": {"rotate": [{"value": -12}, {"time": 0.2, "value": 8}, {"time": 0.4, "value": -12}, {"time": 0.8, "value": -12}]},
        "lower_arm_l": {"rotate": [{"value": -4}, {"time": 0.2, "value": 4}, {"time": 0.4, "value": -4}, {"time": 0.8, "value": -4}]},
        "lower_arm_r": {"rotate": [{"value": 4}, {"time": 0.2, "value": -4}, {"time": 0.4, "value": 4}, {"time": 0.8, "value": 4}]},
    }
    data = {
        "skeleton": {"hash": "cotton_doll_runtime_draft_v1", "spine": "4.2.43", "x": 0, "y": 0, "width": 0, "height": 0, "images": "./images/"},
        "bones": BONES,
        "slots": [{"name": slot, "bone": bone, "attachment": attachment} for slot, bone, attachment in SLOTS],
        "skins": [{"name": "default", "attachments": attachments}, {"name": "skin_outfit_default", "attachments": attachments}],
        "animations": {
            "idle": {"bones": idle_bones},
            "walk": {"bones": walk_bones},
        },
        "cottonDollDraft": {
            "status": "runtime_data_draft_placeholders",
            "sourceDirections": ["front", "front_right_3q", "back", "back_right_3q"],
            "mirrors": {"front_left_3q": "front_right_3q", "back_left_3q": "back_right_3q"},
            "templateActions": ["idle", "walk"],
            "notIncluded": ["real_part_png", "mesh_weights", "ik_constraints", "editable_spine_project", "unity_device_acceptance"],
            "warning": "This is a structural runtime-data draft with placeholder attachment regions. Do not ship or treat as final art."
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
