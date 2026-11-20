"""Visible pose fragments traced from the actual video, not reusable rig parts.
Manual source-pixel polygons by assistant visual review. No old masks, donor
textures, AI fill, mirroring, identity interpolation or motion templates.
"""
from pathlib import Path
import argparse
import hashlib
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent / 'generated_rig' / 'video_f7e82942'
OUT = BASE / 'video_parts_v1'
SHA = '8fc0f8406d6a258640b65d34c5ad7fb0e35f231131d7eec945781dd9d93343e5'
# Polygons trace visible contours. Straight internal cuts are explicit uncertain
# attachment boundaries, NOT inferred shoulder or hip anatomy.
TRACES = {
  0: {
    'arm_A': [(407,299),(389,300),(372,307),(357,318),(347,330),(343,340),(345,350),(351,355),(361,357),(365,360),(372,359),(378,354),(383,344),(390,337),(407,331)],
    'arm_B': [(490,300),(504,302),(513,296),(522,294),(534,296),(543,303),(548,312),(549,321),(545,330),(535,337),(522,342),(508,343),(497,339)],
    'leg_A': [(400,391),(411,384),(424,381),(439,382),(452,387),(462,395),(466,409),(467,421),(475,431),(477,441),(473,448),(460,452),(440,454),(425,454),(418,451),(415,440),(410,426),(404,413),(398,400)],
    'leg_B_fragment': [(388,387),(394,401),(400,413),(407,417),(399,418),(391,415),(386,411),(385,401)]
  },
  8: {
    'arm_A_chest': [(405,300),(414,310),(430,316),(450,307),(471,302),(485,304),(493,310),(497,320),(497,330),(492,339),(480,346),(461,350),(442,350),(429,346),(417,338),(408,329),(401,319)],
    'leg_A': [(381,373),(393,377),(405,382),(417,389),(430,398),(433,402),(426,410),(413,419),(402,424),(400,431),(394,436),(384,437),(375,434),(367,428),(362,419),(358,409),(358,397),(361,386),(368,381),(376,380)],
    'leg_B': [(476,365),(487,362),(497,369),(505,381),(511,389),(521,390),(529,394),(534,401),(535,408),(532,416),(526,423),(517,429),(507,433),(495,434),(487,431),(481,425),(477,417),(471,410),(463,404),(456,398),(467,389)]
  },
  16: {
    'arm_A': [(406,294),(389,295),(373,302),(359,312),(350,324),(347,336),(349,344),(355,349),(366,350),(373,353),(380,351),(385,341),(391,331),(405,322)],
    'arm_B': [(489,296),(504,298),(514,290),(524,289),(536,293),(543,301),(547,311),(546,321),(539,328),(529,333),(514,334),(500,329)],
    'leg_A': [(402,380),(416,374),(431,373),(446,375),(457,383),(463,394),(466,408),(475,414),(480,422),(480,429),(470,436),(453,442),(433,444),(423,440),(417,430),(414,419),(408,412),(401,400),(397,389)],
    'leg_B_fragment': [(392,398),(398,408),(408,419),(414,426),(416,435),(407,434),(397,429),(391,420),(388,409)]
  },
  24: {
    'arm_A_chest': [(404,308),(414,315),(432,321),(449,312),(464,309),(479,310),(489,317),(493,328),(491,337),(482,344),(466,349),(446,350),(432,346),(420,339),(411,329),(403,320)],
    'leg_A': [(380,375),(395,380),(408,386),(420,394),(430,402),(422,412),(410,421),(399,425),(397,432),(389,436),(378,435),(368,430),(361,421),(358,410),(358,399),(361,388),(368,381),(376,382)],
    'leg_B': [(477,370),(489,366),(500,371),(508,383),(513,397),(513,404),(524,407),(530,413),(530,421),(522,428),(510,433),(498,434),(488,430),(483,420),(478,414),(467,405),(461,402),(468,389)]
  },
  32: {
    'arm_A': [(407,289),(390,292),(374,299),(361,309),(353,321),(352,333),(356,343),(365,347),(375,347),(382,350),(387,345),(392,331),(398,321),(409,317)],
    'arm_B': [(490,292),(504,293),(514,287),(525,285),(536,288),(544,295),(548,306),(547,316),(541,324),(530,330),(514,331),(500,327)],
    'leg_A': [(401,374),(415,366),(430,365),(444,368),(455,375),(462,387),(466,402),(468,414),(476,421),(476,429),(469,435),(454,439),(438,440),(427,437),(419,430),(416,420),(411,410),(403,400),(399,387)],
    'leg_B_fragment': [(392,395),(399,407),(408,417),(414,424),(416,434),(407,432),(398,427),(392,418),(389,407)]
  }
}


# Independently reviewed 2x crops: origin (320,275), scale 2.
# Conservative coarse outlines, not subpixel matte or recovered joint cuts.
# Tiny/merged far limbs are deliberately omitted rather than invented.
CYCLE_TRACES_2X = {
  68: {
    'arm_A': [(135,53),(103,77),(78,109),(67,138),(72,164),(86,180),(110,185),(126,181),(138,187),(151,174),(158,145),(170,125),(191,114)],
    'arm_B': [(341,68),(369,65),(394,69),(420,83),(439,102),(446,125),(437,143),(416,152),(392,153),(368,146),(354,133)],
    'leg_A': [(158,244),(179,226),(205,218),(232,220),(259,229),(276,245),(280,267),(276,289),(278,307),(287,326),(284,342),(270,351),(247,357),(218,357),(194,348),(177,331),(170,309),(171,287)],
  },
  69: {
    'arm_A': [(143,54),(120,79),(102,110),(93,139),(95,168),(109,189),(132,203),(155,205),(174,197),(180,180),(181,156),(190,136),(205,123)],
    'arm_B': [(349,83),(375,84),(399,96),(419,111),(428,132),(426,150),(409,161),(385,163),(365,157)],
    'leg_A': [(155,245),(174,229),(200,221),(228,224),(254,234),(272,250),(275,271),(270,294),(267,314),(269,336),(259,349),(235,357),(206,357),(181,347),(164,332),(154,314),(155,291)],
  },
  70: {
    'arm_A_chest': [(167,65),(151,101),(145,129),(147,151),(161,171),(182,186),(204,193),(226,189),(246,176),(261,155),(267,133),(261,116),(244,105),(222,98),(218,80)],
    'leg_A': [(137,204),(167,206),(201,218),(231,238),(248,258),(243,280),(231,301),(230,325),(220,343),(204,352),(181,354),(157,347),(138,334),(127,313),(125,290),(130,269)],
    'leg_B': [(337,191),(355,188),(368,203),(378,224),(377,247),(366,268),(344,288),(325,305),(304,307),(282,297),(260,282),(251,269),(257,248),(280,236),(302,222)],
  },
  71: {
    'arm_A_chest': [(178,48),(166,84),(165,111),(173,135),(192,153),(214,163),(239,172),(263,173),(287,166),(305,152),(311,132),(309,110),(297,92),(280,86),(250,85),(241,66)],
    'leg_A': [(130,192),(160,196),(192,208),(221,225),(239,245),(230,268),(215,292),(211,318),(199,341),(179,351),(157,347),(137,333),(121,313),(111,291),(111,268),(120,241)],
    'leg_B': [(350,157),(370,173),(384,196),(390,220),(381,246),(368,266),(363,289),(350,307),(329,310),(307,300),(286,284),(272,263),(269,242),(281,221),(305,198),(327,178)],
  },
  72: {
    'arm_A_chest': [(189,35),(178,66),(178,95),(186,118),(204,136),(225,148),(248,154),(275,155),(301,151),(321,139),(331,121),(333,102),(329,83),(317,68),(301,63),(280,67),(264,69),(255,54)],
    'leg_A': [(128,190),(157,196),(188,210),(216,225),(235,244),(223,265),(208,287),(199,309),(193,333),(179,343),(157,344),(138,336),(120,320),(108,300),(99,277),(99,254),(109,238),(118,214)],
    'leg_B': [(369,172),(385,192),(395,218),(396,242),(390,262),(388,280),(392,296),(381,307),(361,312),(338,312),(316,305),(298,293),(288,277),(283,256),(288,239),(303,220),(327,198),(349,181)],
  },
  73: {
    'arm_A_chest': [(191,31),(184,59),(184,86),(193,110),(214,128),(239,141),(263,149),(289,148),(315,141),(339,128),(352,110),(357,90),(351,68),(335,53),(318,50),(295,54),(271,62),(261,50)],
    'leg_A': [(119,191),(149,198),(181,213),(212,231),(229,249),(213,264),(192,278),(177,291),(172,310),(156,324),(133,331),(111,326),(96,311),(87,292),(82,270),(86,248),(100,227),(114,208)],
    'leg_B': [(366,176),(384,194),(396,217),(398,239),(412,248),(420,265),(418,283),(406,296),(385,304),(363,306),(341,304),(320,296),(306,281),(298,262),(288,248),(278,240),(296,219),(322,197),(344,183)],
  },
  74: {
    'arm_A_chest': [(197,38),(190,66),(196,91),(211,113),(235,133),(261,147),(288,153),(315,151),(339,143),(355,126),(361,105),(359,83),(347,62),(330,54),(308,58),(286,70),(270,76),(257,62)],
    'leg_A': [(115,191),(108,183),(92,189),(80,205),(70,225),(67,246),(73,263),(89,278),(108,283),(126,280),(146,286),(168,286),(190,279),(207,268),(218,257),(206,239),(181,218),(153,201)],
    'leg_B': [(370,193),(385,214),(390,236),(389,253),(409,256),(423,269),(424,288),(413,306),(395,322),(376,330),(352,333),(329,329),(313,319),(303,301),(296,283),(281,265),(276,259),(299,234),(328,212),(351,199)],
  },
  75: {
    'arm_A_chest': [(190,45),(187,72),(194,99),(210,122),(232,141),(257,156),(284,166),(309,166),(329,157),(343,142),(348,121),(346,100),(335,82),(319,73),(300,75),(280,84),(263,87),(253,73)],
    'leg_A': [(121,197),(110,191),(96,199),(82,220),(74,244),(77,264),(89,278),(108,286),(126,285),(145,295),(168,296),(191,290),(209,281),(224,270),(213,252),(189,230),(161,211)],
    'leg_B': [(371,198),(383,222),(386,247),(382,270),(385,291),(399,310),(394,325),(376,334),(354,339),(330,338),(307,331),(293,316),(284,295),(279,279),(275,273),(300,246),(327,224),(350,209)],
  },
  76: {
    'arm_A_chest': [(189,48),(179,75),(177,103),(184,129),(200,151),(222,168),(247,180),(275,186),(300,181),(317,169),(327,151),(329,128),(325,108),(312,94),(294,91),(272,95),(253,98),(243,83)],
    'leg_A': [(123,202),(111,204),(98,221),(88,243),(85,264),(90,281),(103,292),(121,296),(139,291),(158,303),(181,305),(201,300),(219,290),(234,275),(224,257),(200,237),(171,219),(147,211)],
    'leg_B': [(367,211),(374,235),(371,259),(361,280),(365,297),(374,319),(365,332),(344,338),(320,339),(297,335),(278,325),(268,309),(268,290),(274,277),(294,256),(318,237),(343,221)],
  },
  77: {
    'arm_A_chest': [(177,49),(163,81),(159,111),(162,138),(174,160),(195,179),(222,191),(248,200),(272,197),(287,184),(294,164),(295,142),(289,124),(276,114),(256,111),(231,112),(228,94)],
    'leg_A': [(129,209),(118,207),(109,222),(102,244),(100,265),(105,285),(117,301),(134,307),(148,304),(171,309),(194,307),(218,300),(236,287),(246,271),(241,254),(222,237),(196,225),(164,215)],
    'leg_B': [(365,224),(367,248),(361,272),(352,292),(348,308),(359,320),(351,332),(330,339),(306,339),(283,335),(265,326),(251,312),(252,294),(260,285),(278,278),(303,260),(332,239)],
  },
  78: {
    'arm_A': [(160,38),(140,65),(126,96),(121,125),(123,151),(135,174),(156,185),(183,190),(210,187),(227,179),(231,163),(223,145),(210,126),(206,112),(217,98)],
    'arm_B': [(352,74),(375,88),(396,90),(411,104),(418,125),(416,145),(403,157),(384,162),(363,158)],
    'leg_A': [(149,219),(168,203),(195,197),(222,199),(245,208),(264,224),(270,245),(269,267),(261,286),(248,297),(222,303),(205,314),(194,321),(174,320),(155,310),(140,294),(134,275),(136,251)],
    'leg_B_fragment': [(268,270),(254,284),(233,298),(219,305),(223,318),(238,329),(260,335),(284,335),(307,329),(319,318),(319,299),(314,284),(330,257),(339,240),(322,250),(299,262)],
  },
  79: {
    'arm_A': [(152,41),(132,62),(112,90),(102,121),(100,146),(106,165),(121,177),(143,180),(165,176),(183,164),(188,144),(187,121),(190,103),(205,88)],
    'arm_B': [(351,57),(375,65),(389,64),(408,71),(423,87),(431,107),(433,125),(422,137),(402,143),(379,142),(361,134)],
    'leg_A': [(159,202),(183,182),(211,173),(237,176),(259,187),(276,206),(282,228),(280,249),(269,270),(251,286),(247,306),(237,320),(221,325),(200,321),(180,307),(166,291),(158,271),(159,246),(166,237)],
    'leg_B_fragment': [(248,285),(243,303),(234,318),(223,327),(248,332),(271,331),(290,322),(300,309),(302,293),(296,280),(309,259),(321,242),(302,255),(279,267)],
  },
  80: {
    'arm_A': [(143,45),(120,62),(99,86),(85,111),(80,135),(84,153),(96,165),(113,171),(137,170),(153,162),(161,144),(164,121),(174,102),(193,87)],
    'arm_B': [(350,43),(375,47),(398,45),(421,53),(437,70),(444,90),(443,108),(430,121),(409,128),(386,125),(366,115)],
    'leg_A': [(158,207),(181,185),(209,174),(235,175),(260,186),(279,205),(285,228),(285,252),(278,272),(278,291),(282,306),(275,318),(254,323),(231,319),(207,308),(190,293),(178,273),(174,255),(180,249)],
  },
  81: {
    'arm_A': [(137,44),(112,57),(88,78),(71,100),(64,124),(65,142),(76,153),(95,157),(117,156),(137,148),(148,133),(158,111),(172,100),(193,91)],
    'arm_B': [(347,37),(373,39),(398,34),(421,37),(442,48),(451,66),(451,86),(441,103),(421,114),(397,117),(370,111),(356,100)],
    'leg_A': [(158,209),(178,190),(205,182),(232,184),(258,195),(279,216),(290,239),(293,258),(305,268),(317,281),(316,294),(299,309),(278,321),(257,325),(235,320),(217,308),(204,292),(192,270),(183,250),(173,232)],
    'leg_B_fragment': [(159,251),(170,260),(180,278),(192,296),(202,307),(186,305),(170,298),(159,287),(157,270)],
  },
  82: {
    'arm_A': [(126,48),(99,61),(75,79),(55,102),(45,124),(48,140),(62,151),(82,154),(104,153),(122,145),(133,129),(144,113),(165,106),(185,94)],
    'arm_B': [(345,37),(371,39),(394,32),(418,35),(439,47),(451,65),(451,86),(440,103),(419,116),(394,121),(370,115),(353,104)],
    'leg_A': [(155,237),(170,220),(194,206),(218,202),(243,208),(266,222),(285,244),(294,269),(296,289),(315,298),(322,311),(317,326),(298,339),(272,347),(246,348),(229,339),(216,319),(205,296),(191,274),(177,253)],
    'leg_B_fragment': [(140,227),(149,237),(156,253),(166,270),(176,285),(162,287),(147,282),(135,272),(132,254)],
  },
  83: {
    'arm_A': [(131,45),(105,60),(79,82),(57,107),(49,130),(53,147),(68,160),(88,165),(108,161),(123,149),(136,128),(151,117),(174,105)],
    'arm_B': [(348,40),(376,41),(397,38),(420,45),(438,59),(448,78),(446,98),(433,116),(411,127),(388,130),(366,120)],
    'leg_A': [(155,244),(174,226),(199,216),(225,215),(251,223),(273,240),(287,261),(291,285),(291,303),(305,322),(306,337),(294,347),(271,354),(245,356),(221,352),(204,342),(191,326),(185,306),(181,284),(170,262)],
    'leg_B_fragment': [(142,237),(151,252),(157,268),(166,282),(173,289),(161,291),(149,287),(141,278),(138,263)],
  },
  84: {
    'arm_A': [(137,54),(109,74),(86,100),(70,126),(67,149),(75,169),(91,182),(112,184),(128,179),(140,181),(151,166),(156,145),(168,125),(190,114)],
    'arm_B': [(346,68),(370,63),(393,65),(417,77),(436,93),(447,115),(444,135),(431,148),(410,156),(387,155),(366,147)],
    'leg_A': [(156,245),(175,228),(200,218),(225,217),(250,225),(272,241),(282,260),(284,283),(281,300),(287,320),(286,339),(274,350),(252,357),(228,358),(204,351),(187,337),(175,317),(173,296),(166,272)],
  },
}
for _idx, _pieces in CYCLE_TRACES_2X.items():
    TRACES[_idx] = {_name: [(320 + x / 2, 275 + y / 2) for x, y in _poly]
                    for _name, _poly in _pieces.items()}


def main():
    assert BASE.is_dir()
    OUT.mkdir(exist_ok=True)
    assert hashlib.sha256((BASE / 'source.mp4').read_bytes()).hexdigest() == SHA
    cap = cv2.VideoCapture(str(BASE / 'source.mp4'))
    assert (int(cap.get(3)), int(cap.get(4)), cap.get(5)) == (864, 480, 24.0)
    frames = {}
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i in TRACES:
            frames[i] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        i += 1
    cap.release()
    assert i == 107 and set(frames) == set(TRACES)
    parts = []
    checks = []
    for idx, traces in TRACES.items():
        im = frames[idx]
        im.save(OUT / f'source_{idx:03d}.png')
        rgb = np.array(im)
        annotated = im.copy()
        d = ImageDraw.Draw(annotated)
        for order, (name, polygon) in enumerate(traces.items()):
            ident = f'f{idx:03d}_{name}_visible'
            # One-bit source-space ownership mask. No threshold on foreground
            # RGB, so pale plush/white clothing cannot be erased as background.
            mask_im = Image.new('L', im.size)
            ImageDraw.Draw(mask_im).polygon(polygon, fill=255)
            mask = np.array(mask_im)
            # Local boundary-only white-background rejection. Never thresholds
            # the full character: interior pale fabric is retained unchanged.
            dist_inside = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
            white = (rgb.min(axis=2) > 243) & ((rgb.max(axis=2).astype(int) - rgb.min(axis=2).astype(int)) < 14)
            edge_white = white & (mask > 0) & (dist_inside <= 3.0)
            mask[edge_white] = 0
            mask_im = Image.fromarray(mask)
            rgba = np.dstack([rgb, mask])
            rgba[mask == 0, :3] = 0
            box = mask_im.getbbox()
            Image.fromarray(rgba).crop(box).save(OUT / (ident + '.png'))
            mask_im.save(OUT / (ident + '_mask.png'))
            d.line(polygon + [polygon[0]], fill=['#a835b5','#138490','#cb611c','#4766cc'][order], width=2)
            d.text((box[0], max(0, box[1]-14)), name, fill='#143d4b', stroke_width=1, stroke_fill='white')
            opaque = mask == 255
            exact = bool(np.array_equal(rgba[opaque, :3], rgb[opaque]))
            # Reinsert fragment at its source origin: no transformed pixels.
            back = np.array(im).copy()
            back[opaque] = rgba[opaque, :3]
            reinsertion = bool(np.array_equal(back, rgb))
            checks.append(exact and reinsertion)
            is_arm = name.startswith('arm')
            fragment = 'fragment' in name
            parts.append({
                'id': ident, 'file': ident + '.png', 'maskFile': ident + '_mask.png',
                'sourceFrame': idx, 'sourceFile': f'source_{idx:03d}.png', 'sourceFrameSha256': hashlib.sha256((OUT / f'source_{idx:03d}.png').read_bytes()).hexdigest(),
                'sourceSize': [864, 480], 'time': idx / 24, 'bbox': list(box),
                'polygonSourcePixels': polygon, 'alphaMode': 'binary_manual_contour_boundary_white_cleanup_max3px',
                'removedBoundaryWhitePixels': int(edge_white.sum()),
                'kind': 'arm' if is_arm else 'leg', 'pose': 'chest_crossing' if 'chest' in name else 'crossing_fragment' if fragment else 'extended_visible',
                'evidenceGroup': 'continuous_068_084' if 68 <= idx <= 84 else 'sampled_poses',
                'shapeReview': 'ai_foot_shape_review_required' if (not is_arm and 74 <= idx <= 77) else 'coarse_boundary_review_required',
                'anatomicalIdentity': 'unknown', 'crossFrameIdentityEstablished': False,
                'boundaryConfidence': 'low' if is_arm or fragment else 'medium',
                'manualTraceBy': 'assistant_visual_review_source_pixel_grid',
                'occlusion': 'partial_visible_sliver_only' if fragment else 'shoulder_merged_with_torso_internal_cut_uncertain' if is_arm else 'upper_thigh_occluded_by_shorts',
                'omittedHiddenPixels': True, 'rgbPreserved': exact, 'sourceReinsertionExact': reinsertion,
                'whiteOrShadowBoundaryRisk': True,
                'status': 'pose_evidence_coarse_boundary_review_required',
                'notReusableRigPart': True,
            })
        annotated.save(OUT / f'contours_{idx:03d}.jpg', quality=96)
    sheet = Image.new('RGB', (1200, 5 * 225), '#f2f1ed')
    d = ImageDraw.Draw(sheet)
    for row, idx in enumerate([0, 8, 16, 24, 32]):
        src = frames[idx].crop((320,275,555,465)).resize((235,190))
        sheet.paste(src, (0,row*225+20))
        d.text((8,row*225+3), f'Source frame {idx}', fill='#222222')
        for col,p in enumerate([p for p in parts if p['sourceFrame']==idx]):
            x=245+col*235; y=row*225
            # Include both light and dark half-background for fringe review.
            d.rectangle((x,y+20,x+220,y+210),fill='#24313e')
            d.rectangle((x,y+20,x+110,y+210),fill='#eeece6')
            tile=Image.open(OUT/p['file']).convert('RGBA')
            tile.thumbnail((190,170),Image.Resampling.NEAREST)
            sheet.paste(tile,(x+(220-tile.width)//2,y+25+(170-tile.height)//2),tile)
            d.text((x,y+3),p['id'],fill='#222222')
    sheet.save(OUT/'pose_parts_review.jpg',quality=96)
    for group, name in [(list(range(68, 76)), 'cycle_parts_068_075.jpg'),
                        (list(range(76, 85)), 'cycle_parts_076_084.jpg')]:
        columns = 4
        rows = (len(group) + columns - 1) // columns
        cell_w, cell_h = 235, 225
        cycle_sheet = Image.new('RGB', (columns * cell_w, rows * cell_h), '#f2f1ed')
        cycle_draw = ImageDraw.Draw(cycle_sheet)
        for pos, idx in enumerate(group):
            x, y = (pos % columns) * cell_w, (pos // columns) * cell_h
            cycle_draw.text((x + 8, y + 3), f'Frame {idx:03d} · visible pose fragments', fill='#222222')
            cycle_draw.rectangle((x + 5, y + 25, x + 230, y + 215), fill='#24313e')
            cycle_draw.rectangle((x + 5, y + 25, x + 117, y + 215), fill='#eeece6')
            # Source-space layout: no scaling, identity matching or overlap repair.
            # Both halves show the same visible source fragments over two grounds.
            for part in [p for p in parts if p['sourceFrame'] == idx]:
                tile = Image.open(OUT / part['file']).convert('RGBA')
                box = part['bbox']
                tx, ty = x + box[0] - 320, y + 25 + box[1] - 275
                cycle_sheet.paste(tile, (tx, ty), tile)
        cycle_sheet.save(OUT / name, quality=96, subsampling=0)
    outlines = Image.new('RGB',(864,480*3),'#f2f1ed')
    for j,idx in enumerate([0,8,24]):
        outlines.paste(Image.open(OUT/f'contours_{idx:03d}.jpg'),(0,480*j))
    outlines.save(OUT/'contours_review.jpg',quality=95)
    record={
        'version':2,'taskId':'comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa','sourceVideoSha256':SHA,'characterId':None,
        'sourceVideo':'../source.mp4','sourceCoordinateSystem':'864x480 source pixels, top-left origin, zero-based frame index',
        'status':'video_visible_pose_fragments_not_reusable_rig_parts','frameIndices':list(TRACES),
        'parts':parts,'partCount':len(parts),'reviewImage':'pose_parts_review.jpg','contourReview':'contours_review.jpg',
        'checks':{'decodedSourceSpecsMatch':True,'allOpaqueRGBMatchSource':all(p['rgbPreserved'] for p in parts),'allReinsertionsExact':all(checks),'noSyntheticHiddenPixels':True,'noLegacyMaskOrMotionImports':True},
        'limitations':['Manual coarse polygons: residual white/background or lost fine plush edge may remain; RGB equality is not segmentation accuracy', 'Arm attachment cuts inside torso are uncertain, not recovered shoulders', 'A/B labels do not establish near/far or cross-frame identity', 'No hidden reconstruction, no inpaint, no reuse binding, no fitted animation', 'Floor shadow contamination near soles requires visual review; white rejection only inside <=3px manual-boundary band with minRGB>243 and chroma<14, never full-image removal'],
        'missingObservations':[{'sourceFrame':idx,'kind':'arm','reason':'far arm hidden/merged; no isolated pixels invented'} for idx in [8,24]],
        'nextAssetDecisions':['Chest-crossing arm requires a distinct visible-shape attachment or validated mesh; neutral arm rotation alone is insufficient', 'Crossing back-leg fragments cannot define a complete leg; use expanded views as evidence without treating screen-side as anatomical identity', 'Torso behind chest arm has no visible pixels in these frames; preserve missing region for separate repair'],
        'promotedToRuntime':False
    }
    (OUT/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(record['checks'].values())
    print(json.dumps({'parts':len(parts),'frames':list(TRACES),'checks':record['checks'],'out':str(OUT)},ensure_ascii=False))


# Assistant review of the generated contact sheets, not anatomy or motion fit.
CYCLE_OBSERVATIONS = {
    68: ('two_outer_arm_shapes', 'crossed_legs_one_front_outline', '两侧臂轮廓可见；前层腿遮挡后层腿，不能从窄残片恢复完整肢体。'),
    69: ('outer_arms_moving_inward', 'crossed_legs_separating', '画面左侧臂靠近身体，右侧圆形手部仍可见；双腿开始分开。'),
    70: ('front_bent_arm_transition', 'two_leg_outlines_visible', '画面左侧手臂弯向身体前方；另一侧仅窄轮廓，肩臂内部切线不确定。'),
    71: ('front_chest_arm', 'two_leg_outlines_visible', '胸前弯臂形成明显前层轮廓；双腿展开，另一臂不能独立完整切出。'),
    72: ('front_chest_arm', 'two_leg_outlines_visible', '胸前弯臂覆盖躯干底图；两腿可见，髋上缘仍被短裤遮挡。'),
    73: ('front_chest_arm', 'two_leg_outlines_visible', '胸前臂保持；两脚形状和脚底角度变化，不应只旋转单张脚掌。'),
    74: ('front_chest_arm', 'screen_left_foot_flattened', '画面左侧脚横向压扁、腿脚连接轮廓不稳定；需审查AI形变，不能直接定为真实关节。'),
    75: ('front_chest_arm', 'screen_left_foot_flattened', '画面左侧脚较扁并向外伸；画面右侧脚较竖直，不能据此确定解剖左右或支撑脚。'),
    76: ('front_chest_arm', 'screen_left_foot_flattened', '胸前臂和展开腿仍可见；接地/悬空不能仅凭影子判定。'),
    77: ('front_arm_lowering', 'legs_begin_crossing', '胸前臂下移，弯臂下沿贴近腰；腿开始交叠，短裤边缘仍需独立层。'),
    78: ('arms_opening_transition', 'one_raised_leg_other_foot_visible', '两侧手臂重新展开；画面左侧腿抬到前方，后层脚仍可见。'),
    79: ('two_outer_arm_shapes', 'crossing_both_feet_partly_visible', '两臂分列身体两侧；腿交叉，仍能看到后层脚的局部轮廓。'),
    80: ('two_outer_arm_shapes', 'crossing_both_feet_partly_visible', '前层腿遮挡另一腿上部；后脚下部可见，不建立跨帧身份。'),
    81: ('two_outer_arm_shapes', 'crossed_legs_partial_back_sliver', '前层腿向前摆，后层仅局部脚/腿边缘；内部遮挡切线需精修。'),
    82: ('two_outer_arm_shapes', 'crossed_legs_partial_back_sliver', '前层腿占主要轮廓，后层腿更窄；完整隐藏区不可由当前可见片推得。'),
    83: ('two_outer_arm_shapes', 'crossed_legs_one_front_outline', '前层腿较竖直；后层腿残片不足以恢复完整肢体。'),
    84: ('two_outer_arm_shapes', 'crossed_legs_one_front_outline', '姿态与68帧相近，仍只为重复端点候选，未验收完整循环。'),
}


def cycle_review():
    source = BASE / 'source.mp4'
    if not OUT.is_dir():
        raise FileNotFoundError(f'审阅目录的父目录不存在: {OUT}')
    video_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if video_sha != SHA:
        raise ValueError('固定源视频 SHA256 不匹配')
    indices = list(range(68, 85))
    frames = {}
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise ValueError('无法打开固定源视频')
        fps = cap.get(cv2.CAP_PROP_FPS)
        if (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), fps) != (864, 480, 24.0):
            raise ValueError('固定源视频规格不匹配')
        # 从第0帧顺序解码，不使用随机跳帧定位。
        for idx in range(85):
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'顺序解码在第 {idx} 帧提前结束')
            if idx >= 68:
                frames[idx] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()

    review = OUT / 'cycle_review'
    if not review.parent.is_dir():
        raise FileNotFoundError(f'审阅目录的父目录不存在: {review.parent}')
    review.mkdir(exist_ok=True)
    crop_box = (320, 275, 555, 465)
    scale = 2
    crop_size = ((crop_box[2] - crop_box[0]) * scale,
                 (crop_box[3] - crop_box[1]) * scale)
    records = []
    crops = {}
    for idx in indices:
        original = review / f'source_{idx:03d}.png'
        cropped = review / f'crop_{idx:03d}_2x.png'
        frames[idx].save(original, format='PNG')
        crops[idx] = frames[idx].crop(crop_box).resize(crop_size, Image.Resampling.NEAREST)
        crops[idx].save(cropped, format='PNG')
        records.append({
            'sourceFrame': idx, 'time': idx / fps,
            'sourceFile': original.name,
            'sourceFrameSha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'sourceSize': list(frames[idx].size),
            'cropFile': cropped.name,
            'cropSha256': hashlib.sha256(cropped.read_bytes()).hexdigest(),
            'identity': 'unknown',
            'manualObservations': {
                'armVisibility': CYCLE_OBSERVATIONS[idx][0],
                'legVisibility': CYCLE_OBSERVATIONS[idx][1],
                'note': CYCLE_OBSERVATIONS[idx][2],
                'method': 'assistant_contact_sheet_visual_review',
                'confidence': 'low',
                'crossFrameIdentityEstablished': False,
            },
            'notRuntimeAsset': True,
            'repeatedEndpointCandidate': idx == 84,
        })

    contacts = []
    for group, name in [(list(range(68, 76)), 'contact_068_075.jpg'),
                        (list(range(76, 85)), 'contact_076_084.jpg')]:
        columns = 4
        rows = (len(group) + columns - 1) // columns
        cell_width, cell_height = crop_size[0], crop_size[1] + 28
        sheet = Image.new('RGB', (columns * cell_width, rows * cell_height), '#f2f1ed')
        draw = ImageDraw.Draw(sheet)
        for pos, idx in enumerate(group):
            x = (pos % columns) * cell_width
            y = (pos // columns) * cell_height
            sheet.paste(crops[idx], (x, y + 28))
            suffix = ' | repeated endpoint candidate' if idx == 84 else ''
            draw.text((x + 8, y + 8), f'Frame {idx:03d} | time {idx / fps:.6f}s{suffix}',
                      fill='#222222')
        sheet.save(review / name, format='JPEG', quality=96, subsampling=0)
        contacts.append(name)

    record = {
        'version': 2, 'status': 'visually_reviewed_occlusion_evidence_not_rig',
        'taskId': 'comfy_f7e82942-05e3-4c7e-8e30-e974e2a233fa',
        'characterId': None,
        'sourceVideo': '../../source.mp4', 'sourceVideoSha256': video_sha,
        'sourceCoordinateSystem': '864x480 source pixels, top-left origin, zero-based frame index',
        'decodeMethod': 'sequential_from_frame_0_through_84_no_seek',
        'fps': fps, 'frameIndices': indices, 'sampleCount': len(indices),
        'repeatedEndpointCandidate': 84,
        'samplingNote': '68至84共17张审阅样本；84仅为重复端点候选，未确定周期。',
        'cropBoxSourcePixels': list(crop_box), 'scale': scale,
        'resampling': 'nearest', 'contactSheets': contacts,
        'reviewMethod': 'assistant_visual_review_of_both_contact_sheets',
        'identity': 'unknown',
        'assetDecisions': [
            '分别制作展开臂与胸前弯臂可见形态候选，不能用一张中性侧臂简单旋转代替；最终分为上臂/前臂/手或整臂形态仍需结构验证。',
            '躯干及短裤保持独立底层；胸前臂下方的隐藏身体和髋上缘需要补画，不从其他帧偷换像素冒充当前帧可见证据。',
            '前后层腿交叉需要遮挡层序处理；A/B与屏幕侧不表示固定解剖身份，连续身份未确立。',
            '74至77帧脚掌压扁与转面需对原角色修正，不能将AI视频全部形变原样烘焙；不声称脚锁、接地或动作拟合已完成。',
        ],
        'notRuntimeAsset': True, 'frames': records,
    }
    (review / 'sources.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(review.resolve()), 'sampleCount': len(indices),
                      'contactSheets': [str((review / name).resolve()) for name in contacts]},
                     ensure_ascii=False))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description='视频可见片段提取或独立审阅素材生成')
    parser.add_argument('--cycle-review', action='store_true',
                        help='仅生成68至84帧审阅素材，84为重复端点候选，不运行原提取流程')
    args = parser.parse_args()
    if args.cycle_review:
        cycle_review()
    else:
        main()
