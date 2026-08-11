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

const OUTPUT_FILE = path.join(
    OUTPUT_DIR,
    "puter_test.png"
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
    console.log("");
    console.log("=".repeat(80));
    console.log(text);
    console.log("=".repeat(80));
}

function timeoutPromise(ms) {
    return new Promise((_, reject) => {
        setTimeout(() => {
            reject(
                new Error(
                    `Puter image generation timed out after ${ms / 1000} seconds.`
                )
            );
        }, ms);
    });
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
            "GitHub → Settings → Secrets and variables → Actions"
        );

        process.exit(1);
    }

    console.log("✅ PUTER_AUTH_TOKEN detected.");
    console.log(
        `Token length: ${PUTER_AUTH_TOKEN.length}`
    );

    // --------------------------------------------------------
    // Output directory
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

    printHeader("🔐 INITIALIZING PUTER");

    let puter;

    try {

        puter = init(
            PUTER_AUTH_TOKEN
        );

        console.log(
            "✅ Puter initialized successfully."
        );

    } catch (error) {

        printHeader(
            "❌ PUTER INITIALIZATION FAILED"
        );

        console.error(error);

        process.exit(1);
    }

    // --------------------------------------------------------
    // Generate image
    // --------------------------------------------------------

    printHeader(
        "🧠 STARTING IMAGE GENERATION"
    );

    console.log(
        "Model: gpt-image-2"
    );

    console.log(
        "Quality: medium"
    );

    console.log(
        "Ratio: 9:16"
    );

    console.log(
        `Prompt length: ${PROMPT.length}`
    );

    console.log(
        "⏳ Waiting for Puter..."
    );

    const startTime =
        Date.now();

    try {

        const generationPromise =
            puter.ai.txt2img(
                PROMPT,
                {
                    provider:
                        "openai-image-generation",

                    model:
                        "gpt-image-2",

                    quality:
                        "medium",

                    ratio: {
                        w: 9,
                        h: 16
                    }
                }
            );

        const image =
            await Promise.race([
                generationPromise,
                timeoutPromise(90000)
            ]);

        const elapsed =
            ((Date.now() - startTime) / 1000)
            .toFixed(1);

        console.log(
            `✅ Puter returned image after ${elapsed} seconds.`
        );

        // ----------------------------------------------------
        // Validate response
        // ----------------------------------------------------

        if (
            !image ||
            typeof image !== "object"
        ) {

            throw new Error(
                "Puter returned an invalid image response."
            );
        }

        console.log(
            `Response keys: ${
                Object.keys(image).join(", ")
            }`
        );

        // ----------------------------------------------------
        // Get image source
        // ----------------------------------------------------

        let dataUrl = null;

        if (
            typeof image.src === "string"
        ) {

            dataUrl =
                image.src;

        } else if (
            typeof image.url === "string"
        ) {

            dataUrl =
                image.url;
        }

        if (!dataUrl) {

            throw new Error(
                "Puter response does not contain image.src or image.url."
            );
        }

        console.log(
            "✅ Image source received."
        );

        // ----------------------------------------------------
        // Decode data URL
        // ----------------------------------------------------

        if (
            !dataUrl.startsWith(
                "data:image/"
            )
        ) {

            throw new Error(
                `Unsupported image format: ${dataUrl.substring(0, 100)}`
            );
        }

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

        if (
            !buffer ||
            buffer.length === 0
        ) {

            throw new Error(
                "Decoded image buffer is empty."
            );
        }

        console.log(
            `✅ Image decoded: ${buffer.length} bytes`
        );

        // ----------------------------------------------------
        // Save image
        // ----------------------------------------------------

        fs.writeFileSync(
            OUTPUT_FILE,
            buffer
        );

        console.log(
            `📸 Saved: ${OUTPUT_FILE}`
        );

        // ----------------------------------------------------
        // Verify
        // ----------------------------------------------------

        if (
            !fs.existsSync(
                OUTPUT_FILE
            )
        ) {

            throw new Error(
                "Image file was not created."
            );
        }

        const stats =
            fs.statSync(
                OUTPUT_FILE
            );

        printHeader(
            "🎉 PUTER IMAGE GENERATION SUCCESSFUL"
        );

        console.log(
            `File: ${OUTPUT_FILE}`
        );

        console.log(
            `Size: ${stats.size} bytes`
        );

        console.log(
            `Generation time: ${(
                (Date.now() - startTime) / 1000
            ).toFixed(1)} seconds`
        );

        printHeader(
            "✅ TEST COMPLETE"
        );

    } catch (error) {

        printHeader(
            "❌ PUTER IMAGE GENERATION FAILED"
        );

        console.error(
            "Error:"
        );

        console.error(error);

        if (error?.status) {
            console.error(
                `HTTP Status: ${error.status}`
            );
        }

        if (error?.message) {
            console.error(
                `Message: ${error.message}`
            );
        }

        console.error(
            `Elapsed time: ${(
                (Date.now() - startTime) / 1000
            ).toFixed(1)} seconds`
        );

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

        console.error(error);

        process.exit(1);
    }
);