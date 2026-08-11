const fs = require("fs");
const path = require("path");

const { init } = require("@heyputer/puter.js/src/init.cjs");

// ============================================================
// PUTER CONFIG
// ============================================================

const PUTER_AUTH_TOKEN =
    process.env.PUTER_AUTH_TOKEN;

const OUTPUT_DIR =
    path.join(
        __dirname,
        "puter_test_output"
    );

// Test prompt
const PROMPT = `
A cinematic National Geographic style scientific visualization
of a realistic human brain viewed from a three-quarter angle,
showing detailed natural brain anatomy with subtle illuminated
neural pathways connecting different regions.

Photorealistic scientific documentary quality.
Physically realistic anatomy.
Realistic biological textures.
Professional medical visualization.
Cinematic depth of field.
Dark neutral background.
Subtle blue and warm gold lighting.
One clearly identifiable main subject.
Strong subject separation.
Premium documentary photography aesthetic.

Vertical 9:16 composition.
The brain should dominate the frame.
No text.
No labels.
No typography.
No logo.
No watermark.
No cartoon style.
No fantasy elements.
No excessive neon.
No unnecessary particles.
No distorted anatomy.
No duplicated objects.
No visual clutter.
`;

// ============================================================
// MAIN
// ============================================================

async function main() {

    console.log("=".repeat(80));
    console.log("🎨 PUTER IMAGE GENERATION TEST");
    console.log("=".repeat(80));

    if (!PUTER_AUTH_TOKEN) {

        console.error(
            "❌ PUTER_AUTH_TOKEN is not set."
        );

        console.error(
            "Add PUTER_AUTH_TOKEN to GitHub Secrets."
        );

        process.exit(1);
    }

    console.log(
        "✅ PUTER_AUTH_TOKEN detected."
    );

    fs.mkdirSync(
        OUTPUT_DIR,
        { recursive: true }
    );

    console.log(
        `📁 Output directory: ${OUTPUT_DIR}`
    );

    // --------------------------------------------------------
    // Initialize Puter
    // --------------------------------------------------------

    console.log(
        "🔐 Initializing Puter..."
    );

    const puter = init(
        PUTER_AUTH_TOKEN
    );

    console.log(
        "✅ Puter initialized."
    );

    // --------------------------------------------------------
    // Generate image
    // --------------------------------------------------------

    console.log(
        "🧠 Generating test image..."
    );

    console.log(
        `Prompt length: ${PROMPT.length}`
    );

    try {

        const image =
            await puter.ai.txt2img(
                PROMPT,
                {
                    provider:
                        "openai-image-generation",

                    model:
                        "gpt-image-1-mini",

                    quality:
                        "medium",

                    ratio: {
                        w: 9,
                        h: 16
                    }
                }
            );

        console.log(
            "✅ Puter returned image."
        );

        // ----------------------------------------------------
        // Extract image data
        // ----------------------------------------------------

        if (
            !image ||
            !image.src
        ) {

            throw new Error(
                "Puter returned an invalid image object."
            );
        }

        const dataUrl =
            image.src;

        if (
            !dataUrl.startsWith(
                "data:image/"
            )
        ) {

            throw new Error(
                "Returned image is not a data URL."
            );
        }

        console.log(
            "✅ Image data received."
        );

        // ----------------------------------------------------
        // Convert data URL to PNG
        // ----------------------------------------------------

        const commaIndex =
            dataUrl.indexOf(",");

        if (
            commaIndex === -1
        ) {

            throw new Error(
                "Invalid image data URL."
            );
        }

        const base64Data =
            dataUrl.substring(
                commaIndex + 1
            );

        const buffer =
            Buffer.from(
                base64Data,
                "base64"
            );

        // ----------------------------------------------------
        // Save image
        // ----------------------------------------------------

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
        console.log(
            "🎉 IMAGE GENERATED SUCCESSFULLY"
        );
        console.log("=".repeat(80));

        console.log(
            `Saved: ${outputPath}`
        );

        console.log(
            `Size: ${buffer.length} bytes`
        );

        console.log("=".repeat(80));

    } catch (error) {

        console.error("=".repeat(80));
        console.error(
            "❌ PUTER IMAGE GENERATION FAILED"
        );
        console.error("=".repeat(80));

        console.error(
            error
        );

        console.error("=".repeat(80));

        process.exit(1);
    }
}

main();