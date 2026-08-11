const fs = require("fs");
const path = require("path");

const { init } = require("@heyputer/puter.js/src/init.cjs");

// ============================================================
// PUTER CONFIG
// ============================================================

const PUTER_AUTH_TOKEN =
    process.env.PUTER_AUTH_TOKEN;

const PROMPT =
    process.env.PUTER_IMAGE_PROMPT;

const OUTPUT_PATH =
    process.env.PUTER_OUTPUT_PATH;

const SEED =
    process.env.PUTER_IMAGE_SEED || "0";

const MODEL =
    process.env.PUTER_IMAGE_MODEL ||
    "gpt-image-2";

const QUALITY =
    process.env.PUTER_IMAGE_QUALITY ||
    "medium";

const TIMEOUT_MS = 120000;


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

    printHeader(
        "🎨 PUTER PRODUCTION IMAGE GENERATOR"
    );

    // --------------------------------------------------------
    // Validate environment
    // --------------------------------------------------------

    if (!PUTER_AUTH_TOKEN) {

        throw new Error(
            "PUTER_AUTH_TOKEN is missing."
        );

    }

    if (!PROMPT) {

        throw new Error(
            "PUTER_IMAGE_PROMPT is missing."
        );

    }

    if (!OUTPUT_PATH) {

        throw new Error(
            "PUTER_OUTPUT_PATH is missing."
        );

    }

    console.log(
        "✅ PUTER_AUTH_TOKEN detected."
    );

    console.log(
        `Token length: ${PUTER_AUTH_TOKEN.length}`
    );

    console.log(
        `Model: ${MODEL}`
    );

    console.log(
        `Quality: ${QUALITY}`
    );

    console.log(
        "Ratio: 9:16"
    );

    console.log(
        `Seed: ${SEED}`
    );

    console.log(
        `Prompt length: ${PROMPT.length}`
    );

    console.log(
        `Output: ${OUTPUT_PATH}`
    );


    // --------------------------------------------------------
    // Prepare output directory
    // --------------------------------------------------------

    const outputDir =
        path.dirname(
            OUTPUT_PATH
        );

    fs.mkdirSync(
        outputDir,
        {
            recursive: true
        }
    );


    // --------------------------------------------------------
    // Initialize Puter
    // --------------------------------------------------------

    printHeader(
        "🔐 INITIALIZING PUTER"
    );

    const puter =
        init(
            PUTER_AUTH_TOKEN
        );

    console.log(
        "✅ Puter initialized successfully."
    );


    // --------------------------------------------------------
    // Generate image
    // --------------------------------------------------------

    printHeader(
        "🧠 GENERATING IMAGE"
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
                        MODEL,

                    quality:
                        QUALITY,

                    ratio:
                        {
                            w: 9,
                            h: 16
                        }
                }
            );

        const image =
            await Promise.race(
                [
                    generationPromise,
                    timeoutPromise(
                        TIMEOUT_MS
                    )
                ]
            );

        const elapsed =
            (
                (Date.now() - startTime)
                / 1000
            ).toFixed(1);

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
        // Extract image source
        // ----------------------------------------------------

        let dataUrl = null;

        if (
            typeof image.src === "string"
        ) {

            dataUrl =
                image.src;

        }
        else if (
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
        // Decode image
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

        }
        else {

            throw new Error(
                "Unsupported Puter image response format."
            );

        }


        if (
            !buffer ||
            buffer.length < 1000
        ) {

            throw new Error(
                "Generated image buffer is empty or invalid."
            );

        }

        console.log(
            `✅ Image decoded: ${buffer.length} bytes`
        );


        // ----------------------------------------------------
        // Save image
        // ----------------------------------------------------

        fs.writeFileSync(
            OUTPUT_PATH,
            buffer
        );

        console.log(
            `📸 Saved: ${OUTPUT_PATH}`
        );


        // ----------------------------------------------------
        // Verify file
        // ----------------------------------------------------

        if (
            !fs.existsSync(
                OUTPUT_PATH
            )
        ) {

            throw new Error(
                "Image file was not created."
            );

        }

        const stats =
            fs.statSync(
                OUTPUT_PATH
            );


        printHeader(
            "🎉 PUTER IMAGE GENERATION SUCCESSFUL"
        );

        console.log(
            `File: ${OUTPUT_PATH}`
        );

        console.log(
            `Size: ${stats.size} bytes`
        );

        console.log(
            `Generation time: ${
                (
                    (Date.now() - startTime)
                    / 1000
                ).toFixed(1)
            } seconds`
        );

        console.log(
            `Seed: ${SEED}`
        );

        printHeader(
            "✅ IMAGE COMPLETE"
        );

    }
    catch (error) {

        printHeader(
            "❌ PUTER IMAGE GENERATION FAILED"
        );

        console.error(
            error
        );

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
            `Elapsed time: ${
                (
                    (Date.now() - startTime)
                    / 1000
                ).toFixed(1)
            } seconds`
        );

        process.exit(1);

    }

}


// ============================================================
// RUN
// ============================================================

main().catch(
    (error) => {

        console.error("");
        console.error(
            "❌ UNEXPECTED ERROR"
        );

        console.error(
            error
        );

        process.exit(1);

    }
);