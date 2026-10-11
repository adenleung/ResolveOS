# Pixel room attribution

Upstream: https://github.com/pixel-agents-hq/pixel-agents
Checkpoint: 3537e140c2094761beae748592aeb92ece8edfdd (inspected 2026-10-04).

The BFS pathfinder is adapted from upstream `webview-ui/src/office/layout/tileMap.ts`.
Character sheet frame layout follows upstream `sprites/spriteData.ts` (walk,
typing, reading; left mirrors right). The MIT copyright notice is included here.
The six character sheets are upstream adaptations of JIK-A-4's MetroCity pack:
https://jik-a-4.itch.io/metrocity-free-topdown-character-pack
The author's page explicitly lists Creative Commons Zero v1.0 Universal and
permits commercial use. Credit: JIK-A-4 and Pixel Agents / Pablo De Lucca.

No upstream furniture, floors, pets, fonts, promotional images or screenshots
are redistributed. Furniture provenance is not independently established by
the repository's code license. ResolveOS office furnishings are original canvas
drawings. The seventh character uses a color variation of the first sheet.

ResolveOS uses a focused browser-only canvas adaptation instead of upstream's
full OfficeState/editor/HookProvider runtime. That runtime also includes terminal
agent discovery, wandering, editor tools and extension/CLI messaging that are
unnecessary here. No VS Code runtime, Phaser or coding-agent terminal controls
are imported. Seven fixed roles and serialized handoffs use the same 4-connected
grid and sprite-frame conventions with ResolveOS-specific visual states.
