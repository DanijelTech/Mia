# Avatar models

The HUD expects these files here (they are **not** committed; run
`server/scripts/fetch-avatar-assets.sh`):

| file | source | purpose |
|---|---|---|
| `mia-female.glb` | `readyplayerme/visage` v2.0.0 `public/female.glb` | female avatar, Mixamo rig, 72 ARKit/Oculus blendshapes, modular hair/glasses/top/bottom/footwear |
| `mia-female-idle.glb` | `readyplayerme/visage` v2.0.0 `public/femaleIdle.glb` | idle animation |

The upstream repository is MIT-licensed. The sample avatar is a Ready Player
Me demo asset; keep the upstream provenance and verify Ready Player Me's
current terms before redistributing the model itself. The code in this
repository only downloads it to the local machine.

To use an Avaturn T2 export, drop its `.glb` here and select it in
`/hud/avatar.html`. Avaturn naming is supported by the wardrobe layer
(`avaturn_hair_*`, `avaturn_look_0`, `avaturn_shoes_0`); T2 adds ARKit
blendshapes and therefore facial lip sync.

One female GLB is enough for the whole roster: the nine characters
(`characters.js`), ten procedural wigs (`hair.js`) and the garment/robot props
(`garments.js`) are generated around whichever rig is loaded. Extra female
GLBs are still useful for a different face or body and appear automatically in
the model selector.
