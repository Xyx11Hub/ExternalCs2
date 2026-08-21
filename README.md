# CS2 External ESP Overlay

A single-file, high-performance external ESP (Extra Sensory Perception) overlay for Counter-Strike 2 built with **Python** and **PyQt6**. Designed for smooth frame rates, lightweight execution, and clean visualization without external configuration files.

---

## 🚀 Features

* **Single-File Architecture**: Everything (rendering, memory reading, math, and configuration) is contained within a single Python script.
* **Bounding Box ESP**: Visual indicators for player entities with custom visibility check colors (Visible vs. Occluded/Hidden).
* **Cornered Box Rendering**: Stylized corner-only bounding boxes for a minimal HUD layout.
* **Skeleton Overlay**: Real-time 2D bone structure mapping using screen projection matrix logic.
* **Dynamic Health Bar**: Displays remaining health next to player entities with background contrast.
* **Distance Indicator**: Text readout showing exact player distance in meters with shadow rendering for maximum legibility.
* **High Refresh Rate**: Internal polling loop configured at 8ms (~125 FPS refresh rate).

---

## 🛠️ Technology Stack

* **Language**: Python 3.10+
* **GUI / Rendering**: PyQt6 (`QPainter`, `QColor`)
* **Target Game**: Counter-Strike 2 (64-bit)

---

## ⚙️ In-Script Configuration Parameters

All display, performance, and overlay colors are configured directly at the top of the main script:

### 🎯 Performance & Render Distance
| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `MAX_DIST_M` | `120.0` | Maximum distance (in meters) to render player entities |
| `POLL_MS` | `8` | Memory reading & repainting interval in milliseconds (~125 FPS) |

### 📦 Bounding Box Settings
| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `CORNER_BOX` | `True` | Draws stylized corner boxes instead of full rectangular frames |
| `BOX_THICKNESS` | `2` | Stroke width for box outlines (in pixels) |
| `C_BOX_VIS` | `RGBA(0, 255, 80, 220)` | Box color when the entity is visible |
| `C_BOX_HID` | `RGBA(255, 50, 50, 220)` | Box color when the entity is occluded / behind cover |

### 🦴 Skeleton Settings
| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `SKEL_THICKNESS` | `2` | Line thickness for bone connections (in pixels) |
| `C_SKELETON` | `RGBA(255, 255, 255, 170)` | Color applied to skeleton line pairs |
| `SKEL_PAIRS` | *17 Bone Pairs* | Index pairs mapping head, spine, arms, and legs |
| `NEEDED_BONES` | *Frozenset* | Auto-computed set of unique bone IDs to optimize memory reads |

### 💚 Health Bar Settings
| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `HPBAR_W` | `3` | Width of the health bar indicator (in pixels) |
| `HPBAR_GAP` | `3` | Offset distance from the entity bounding box |
| `C_HP_BG` | `RGBA(30, 30, 30, 180)` | Background bar color |
| `C_HP_FILL` | `RGBA(60, 220, 80, 230)` | Foreground health fill color |

### 🏷️ Distance & Typography
| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| `FONT_DIST_SIZE` | `8` | Font size (in points) for distance text |
| `C_DIST_TEXT` | `RGBA(255, 255, 255, 255)` | Primary distance text color (White) |
| `C_DIST_SHADOW` | `RGBA(0, 0, 0, 180)` | Text shadow color for contrast on light backgrounds |

---

## 📋 Prerequisites & Quickstart

1. **Requirements**:
   * Python 3.10 or higher
   * Counter-Strike 2 running in **Borderless Windowed** mode
