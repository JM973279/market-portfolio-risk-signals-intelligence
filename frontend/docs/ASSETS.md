# Frontend assets

`public/images/seoul-header.webp` is an AI-generated decorative Seoul/Namsan
header, not market evidence or a current camera image. Generated with the built-in
imagegen tool, then converted to WebP with the installed Sharp package (~182 KB).

Final prompt:
> Use case: photorealistic-natural. Asset type: wide cropped background photograph for a premium institutional financial dashboard header. Primary request: Seoul city skyline with recognizable N Seoul Tower on wooded Namsan hill, subtle soft early evening pastel sky, distant modern skyline. Composition: panoramic, tower and hill on the right half, pale blue open sky and faint city haze on left half suitable for navy UI text overlay. Restrained blue gray, soft peach highlights, photographic realism. No text, numbers, charts, logos, UI, watermark or borders. Landscape 3:1 composition.

`public/fonts/PretendardVariable.woff2`: Pretendard v1.3.9, distributed under the
SIL Open Font License retained at `public/fonts/OFL.txt`. Loaded through
`next/font/local`; no runtime font CDN request is needed. Source:
https://github.com/orioncactus/pretendard/tree/v1.3.9

Country flags and navigation icons are local SVG components.
