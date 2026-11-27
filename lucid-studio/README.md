# Lucid Studio

Lucid Studio brings ten editing and creation programs into one launcher. The desktop application opens editors in separate windows or as tabs. The browser edition launches the same program families from the Studio home screen.

## Downloads

- [Integrated Windows x64 portable ZIP](https://github.com/WingedhussarYG/Hyeonjin-Jeong/releases/download/lucid-studio-1.1.0/Lucid-Studio-1.1.0-Windows-x64.zip)
- [Complete development source, including the launcher](https://github.com/WingedhussarYG/Hyeonjin-Jeong/releases/download/lucid-studio-1.1.0/Lucid-Studio-1.1.0-Source.zip)
- [All ten standalone editors and SHA-256 checksums](https://github.com/WingedhussarYG/Hyeonjin-Jeong/releases/tag/lucid-studio-1.1.0)

## Programs and formats

| Program | Role and comparable applications | Formats and workflows |
| --- | --- | --- |
| **Writer** | Word processing and Korean documents. Alternatives for selected Hancom Hangul and Microsoft Word workflows. | Native HWP/HWPX/HML editing uses the Korean document engine. DOCX, DOC, ODT and RTF use the Office engine. PDF has a separate reading and annotation workflow. HML saving depends on the document features. |
| **Calc** | Spreadsheets, calculations and charts. Comparable to Microsoft Excel and LibreOffice Calc. | XLSX, XLS, ODS and CSV. Formula compatibility and advanced objects depend on the workbook. Apple Numbers files may expose a readable preview. |
| **Impress** | Slide authoring and presentations. Comparable to Microsoft PowerPoint and LibreOffice Impress. | PPTX, PPT and ODP. Keynote import uses the available engine filter or embedded preview assets. Advanced objects may change on export. |
| **Pixel** | Raster image and layer editing. Comparable to Adobe Photoshop. | Native LPX projects, PSD/PSB import with feature-dependent layer support, common raster formats including PNG, JPEG and WebP. |
| **Vector** | Paths, illustration and artboards. Comparable to Adobe Illustrator and Inkscape. | Native LVX projects and SVG. PDF-compatible Illustrator files, PDF and EPS have format-specific import limits. |
| **Press** | Page layout and publications. Comparable to Adobe InDesign and Affinity Publisher. | Native LPD projects and IDML interchange. INDD preview or recovery depends on the data embedded in the original. |
| **Cut** | Multitrack video and audio editing. Comparable to Adobe Premiere Pro and DaVinci Resolve’s editing workspace. | LCUT projects. Import video and audio such as MP4, MOV, MKV, WebM, WAV and MP3. Sequence interchange includes supported EDL and Final Cut Pro XML constructs. Desktop media conversion uses FFmpeg. Browser export depends on available codecs. |
| **Stage** | 3D staging, posing, cameras and rendering. Comparable to selected Blender scene-layout workflows. | LSTAGE scenes. Supported model imports include GLB/glTF, OBJ, FBX, STL and PLY. Rendering produces images or video according to the selected renderer. |
| **Board** | Reference boards, mood boards and storyboards. Comparable to PureRef and Milanote. | LBOARD projects with placed images and video, including PNG, JPEG, WebP, MP4 and WebM subject to codec support. PNG stills and supported video exports can be used in other editors. |
| **Create** | Model-driven generation of images, video, audio and 3D assets. Comparable to Adobe Firefly and ArtCraft generation workflows. | Local demonstrations generate PNG images, WAV audio, GLB models and MP4 or WebM video depending on encoder support. Remote inputs and outputs depend on the selected model and provider. Remote generation requires network access and the user’s own provider credentials. |

## Interface languages

The language selector offers **Korean, British English, German, French, Spanish, Japanese and Simplified Chinese**. In the web edition the selection is saved for the current origin. The desktop launcher shares its preference with its editor windows. The Office engine loads the language pack when an engine session opens.

## Source layout

- `web/`, `desktop/` and `engine-payloads/` contain the Office interfaces, Electron integration and pinned document-engine payload.
- `studio/web/` contains the web launcher, browser integrations and editor front ends.
- `native-app/` contains the desktop launcher, preload scripts, Office host, Suite host and the ten editing and creation programs from the verified desktop distribution.
- `standalone-suite-app/` contains the independent Lucid Suite launcher, its four editor programs and their desktop host.
- `localisation/` contains the shared interface code, offline dictionaries, desktop menu integration and LibreOffice language packs.
- `scripts/` contains assembly, offline packaging and verification tools.

Run `python3 scripts/assemble-studio.py` and `node scripts/preview-studio.mjs --port 3000` to use the integrated web edition locally. Open `http://localhost:3000/`. The preview serves local editor assets. Account features require the hosted services.

To build a Windows portable ZIP, run `python3 scripts/package-studio-windows.py Lucid-Studio-Windows-x64.zip` with Python 3.11 or later and 7-Zip installed. The build verifies the upstream Electron distribution before replacing the application resources. Extract the entire ZIP, then launch **Lucid Studio.exe**.

Build the ten standalone browser editors and their download catalogue with `python3 scripts/build-studio-downloads.py ./release-files`. Use the optional `--native` and `--source` arguments to include the current integrated Windows and source ZIPs in the local catalogue.

See the program-specific notices in `studio/licenses/`, `web/` and `native-app/licenses/`. LibreOffice language resources come from the Ubuntu LibreOffice 24.2.7 language packages. Their distribution notice is included in `localisation/engine/COPYRIGHT`. Product names in the comparison table identify familiar workflows.
