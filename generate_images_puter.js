const fs = require("fs");
const path = require("path");

const { init } = require("@heyputer/puter.js/src/init.cjs");

const OUTPUT_DIR = path.join(
    __dirname,
    "puter_test_output"
);

const PROMPT = `
Photorealistic cinematic scientific documentary visualization
of a real human brain in a dark professional medical laboratory
environment, three-quarter view.

Extremely realistic human brain anatomy,
natural biological textures,
realistic blood vessels and tissue detail,
high-end medical visualization,
National Geographic documentary quality,
cinematic photography,
physically realistic lighting,
subtle deep blue and warm gold illumination,
strong subject separation,
shallow depth of field.

The brain is the single dominant subject,
large and clearly visible,
centered in the vertical frame,
realistic scale and perspective.

Vertical 9:16 composition.
Premium documentary photography.
No text.
No labels.
No typography.
No logo.
No watermark.
No cartoon.
No fantasy.
No excessive neon.
No glowing fantasy effects.
No distorted anatomy.
No duplicated objects.
No visual clutter.
`;

async function main() {

    console.log("=".repeat(80));
    console.log("🎨 PUTER IMAGE TEST");
    console.log("=".repeat(80));

    fs.mkdirSync(
        OUTPUT_DIR,
        { recursive: true }
    );

    console.log("Generating test image...");

    try {

        const puter = init();

        const image =
            await puter.ai.txt2img(
                PROMPT,
                {
                    model: "gpt-image-1-mini",
                    quality: "medium",
                    test_mode: true
                }
            );

        if (!image || !image.src) {
            throw new Error(
                "Puter returned no image."
            );
        }

        const dataUrl = image.src;

        if (!dataUrl.startsWith("data:image/")) {
            throw new Error(
                "Unexpected image format."
            );
        }

        const commaIndex =
            dataUrl.indexOf(",");

        const base64 =
            dataUrl.substring(
                commaIndex + 1
            );

        const buffer =
            Buffer.from(
                base64,
                "base64"
            );

        const outputPath =
            path.join(
                OUTPUT_DIR,
                "puter_test.png"
            );

        fs.writeFileSync(
            outputPath,
            buffer
        );

        console.log("=".repeat(80));
        console.log("✅ IMAGE GENERATED");
        console.log("=".repeat(80));
        console.log(`Saved: ${outputPath}`);
        console.log(
            `Size: ${buffer.length} bytes`
        );
        console.log("=".repeat(80));

    } catch (error) {

        console.error("=".repeat(80));
        console.error("❌ PUTER TEST FAILED");
        console.error("=".repeat(80));
        console.error(error);
        console.error("=".repeat(80));

        process.exit(1);
    }
}

main();