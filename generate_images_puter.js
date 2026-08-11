const fs = require("fs");
const path = require("path");

const { init } = require("@heyputer/puter.js/src/init.cjs");

// ============================================================
// PUTER CONFIG
// ============================================================

const PUTER_AUTH_TOKEN =
    process.env.PUTER_AUTH_TOKEN;

const OUTPUT_DIR = path.join(
    __dirname,
    "puter_test_output"
);

// ============================================================
// TEST PROMPT
// ============================================================

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
// HELPERS
// ============================================================

function printHeader(text) {
    console.log("=".repeat(80));
    console.log(text);
    console.log("=".repeat(80));
}

// ============================================================
// MAIN
// ============================================================

async function main() {

    printHeader("🎨 PUTER IMAGE GENERATION TEST");

    // --------------------------------------------------------
    // Check token
    // --------------------------------------------------------

    if (!PUTER_AUTH_TOKEN) {

        console.error(
            "❌ PUTER_AUTH_TOKEN is missing."
        );

        console.error(
            "Add PUTER_AUTH_TOKEN to GitHub:"
        );

        console.error(
            "Settings → Secrets and variables → Actions"
        );

        process.exit(1);
    }

    console.log(
        "✅ PUTER_AUTH_TOKEN detected."
    );

    // Never print the actual token.
    console.log(
        `Token length: ${PUTER_AUTH_TOKEN.length}`
    );

    // --------------------------------------------------------
    // Prepare output directory
    // --------------------------------------------------------

    fs.mkdirSync(
        OUTPUT_DIR,
        {
            recursive: true
        }
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

    let puter;

    try {

        puter = init(
            PUTER_AUTH_TOKEN
        );

        console.log(
            "✅ Puter initialized."
        );

    } catch (error) {

        printHeader(
            "❌ PUTER INITIALIZATION FAILED"
        );

        console.error(
            error
        );

        process.exit(1);
    }

    // --------------------------------------------------------
    // Generate image
    // --------------------------------------------------------

    printHeader(
        "🧠 GENERATING TEST IMAGE"
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
            "✅ Puter returned an image."
        );

        // ----------------------------------------------------
        // Validate response
        // ----------------------------------------------------

        if (
            !image ||
            typeof image !== "object"
        ) {

            throw new Error(
                "Puter returned an invalid response."
            );
        }

        console.log(
            `Response keys: ${Object.keys(image).join(", ")}`
        );

        // ----------------------------------------------------
        // Extract image source
        // ----------------------------------------------------

        let dataUrl = null;

        if (
            typeof image.src === "string"
        ) {

            dataUrl = image.src;

        } else if (
            typeof image.url === "string"
        ) {

            dataUrl = image.url;
        }

        if (!dataUrl) {

            throw new Error(
                "Puter response does not contain an image src/url."
            );
        }

        console.log(
            "✅ Image source received."
        );

        // ----------------------------------------------------
        // Handle data URL
        // ----------------------------------------------------

        let buffer;

        if (
            dataUrl.startsWith(
                "data:image/"
            )
        ) {

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

            buffer =
                Buffer.from(
                    base64Data,
                    "base64"
                );

        } else {

            throw new Error(
                `Unsupported image response format: ${dataUrl.substring(0, 100)}`
            );
        }

        if (
            !buffer ||
            buffer.length === 0
        ) {

            throw new Error(
                "Image buffer is empty."
            );
        }

        console.log(
            `✅ Image data decoded: ${buffer.length} bytes`
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

        // ----------------------------------------------------
        // Verify file
        // ----------------------------------------------------

        if (
            !fs.existsSync(
                outputPath
            )
        ) {

            throw new Error(
                "Image file was not created."
            );
        }

        const stats =
            fs.statSync(
                outputPath
            );

        printHeader(
            "🎉 PUTER IMAGE GENERATED SUCCESSFULLY"
        );

        console.log(
            `📸 File: ${outputPath}`
        );

        console.log(
            `📦 Size: ${stats.size} bytes`
        );

        printHeader(
            "✅ PUTER TEST COMPLETE"
        );

    } catch (error) {

        printHeader(
            "❌ PUTER IMAGE GENERATION FAILED"
        );

        console.error(
            "Error:"
        );

        console.error(
            error
        );

        if (
            error &&
            error.status
        ) {

            console.error(
                `HTTP Status: ${error.status}`
            );
        }

        if (
            error &&
            error.message
        ) {

            console.error(
                `Message: ${error.message}`
            );
        }

        printHeader(
            "PUTER TEST FAILED"
        );

        process.exit(1);
    }
}

// ============================================================
// RUN
// ============================================================

main().catch(
    (error) => {

        console.error(
            "❌ Unexpected error:"
        );

        console.error(
            error
        );

        process.exit(1);
    }
);