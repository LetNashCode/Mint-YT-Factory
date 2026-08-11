const fs = require("fs");
const path = require("path");

const {
    init
} = require("@heyputer/puter.js/src/init.cjs");


// ============================================================
// PUTER CONFIG
// ============================================================

const PUTER_AUTH_TOKEN =
    process.env.PUTER_AUTH_TOKEN;

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
// DIAGNOSTIC PROMPT
// ============================================================
//
// IMPORTANT:
// Keep this intentionally short for the first test.
// Do NOT use PUTER_IMAGE_PROMPT yet.
// Do NOT pass the long 2772-character prompt.
//
// ============================================================

const PROMPT =
    "A realistic cinematic close-up of a human eye.";


// ============================================================
// HELPERS
// ============================================================

function printHeader(text) {

    console.log("");
    console.log("=".repeat(80));
    console.log(text);
    console.log("=".repeat(80));

}


function sleep(ms) {

    return new Promise(
        resolve => setTimeout(resolve, ms)
    );

}


function validateEnvironment() {

    if (!PUTER_AUTH_TOKEN) {

        throw new Error(
            "PUTER_AUTH_TOKEN is missing."
        );

    }

    if (!OUTPUT_PATH) {

        throw new Error(
            "PUTER_OUTPUT_PATH is missing."
        );

    }

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

    validateEnvironment();


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
        `Prompt: ${PROMPT}`
    );

    console.log(
        `Output: ${OUTPUT_PATH}`
    );


    // --------------------------------------------------------
    // Prepare output directory
    // --------------------------------------------------------

    const outputDir =
        path.dirname(
            path.resolve(
                OUTPUT_PATH
            )
        );

    fs.mkdirSync(
        outputDir,
        {
            recursive: true
        }
    );


    // --------------------------------------------------------
    // Remove previous output
    // --------------------------------------------------------

    try {

        if (
            fs.existsSync(
                OUTPUT_PATH
            )
        ) {

            fs.unlinkSync(
                OUTPUT_PATH
            );

        }

    }
    catch (error) {

        console.warn(
            "⚠️ Could not remove previous output:",
            error.message
        );

    }


    // --------------------------------------------------------
    // Initialize Puter
    // --------------------------------------------------------

    printHeader(
        "🔐 INITIALIZING PUTER"
    );

    let puter;

    try {

        puter =
            init(
                PUTER_AUTH_TOKEN
            );

    }
    catch (error) {

        throw new Error(
            `Failed to initialize Puter: ${
                error?.message || error
            }`
        );

    }

    if (!puter) {

        throw new Error(
            "Puter initialization returned an empty client."
        );

    }

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
        "⏳ Sending image generation request..."
    );


    const startTime =
        Date.now();


    try {

        /*
         * ====================================================
         * MINIMAL PUTER IMAGE REQUEST
         * ====================================================
         *
         * Deliberately NOT using:
         *
         * provider
         * puter_output_path
         * long prompt
         *
         * This isolates the Puter SDK request itself.
         *
         * ====================================================
         */

        const generationPromise =
            puter.ai.txt2img(
                PROMPT,
                {
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


        const timeoutPromise =
            new Promise(
                (_, reject) => {

                    setTimeout(
                        () => {

                            reject(
                                new Error(
                                    `Puter image generation timed out after ${
                                        TIMEOUT_MS / 1000
                                    } seconds.`
                                )
                            );

                        },
                        TIMEOUT_MS
                    );

                }
            );


        const result =
            await Promise.race(
                [
                    generationPromise,
                    timeoutPromise
                ]
            );


        const elapsed =
            (
                (Date.now() - startTime)
                / 1000
            ).toFixed(1);


        console.log(
            `✅ Puter generation completed after ${elapsed} seconds.`
        );


        // ----------------------------------------------------
        // Inspect response
        // ----------------------------------------------------

        if (!result) {

            throw new Error(
                "Puter returned an empty response."
            );

        }


        console.log(
            "Response type:",
            typeof result
        );


        if (
            typeof result === "object"
        ) {

            console.log(
                `Response keys: ${
                    Object.keys(result).join(", ")
                }`
            );

        }


        // ----------------------------------------------------
        // Extract image source
        // ----------------------------------------------------

        let dataUrl =
            null;


        if (
            typeof result === "string"
        ) {

            dataUrl =
                result;

        }
        else if (
            typeof result.src === "string"
        ) {

            dataUrl =
                result.src;

        }
        else if (
            typeof result.url === "string"
        ) {

            dataUrl =
                result.url;

        }


        if (!dataUrl) {

            throw new Error(
                "Puter completed but no image source was returned."
            );

        }


        // ----------------------------------------------------
        // Handle data URL
        // ----------------------------------------------------

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
                    "Invalid image data URL returned by Puter."
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
                buffer.length < 1000
            ) {

                throw new Error(
                    "Generated image buffer is empty or invalid."
                );

            }


            fs.writeFileSync(
                OUTPUT_PATH,
                buffer
            );


            console.log(
                `📸 Saved image: ${OUTPUT_PATH}`
            );

        }


        // ----------------------------------------------------
        // Handle URL response
        // ----------------------------------------------------

        else if (
            dataUrl.startsWith(
                "http://"
            ) ||
            dataUrl.startsWith(
                "https://"
            )
        ) {

            console.log(
                "🌐 Puter returned an image URL."
            );

            console.log(
                `URL: ${dataUrl}`
            );


            /*
             * Download using native fetch.
             */

            const response =
                await fetch(
                    dataUrl
                );


            if (
                !response.ok
            ) {

                throw new Error(
                    `Failed to download generated image. HTTP ${response.status}`
                );

            }


            const arrayBuffer =
                await response.arrayBuffer();


            const buffer =
                Buffer.from(
                    arrayBuffer
                );


            if (
                buffer.length < 1000
            ) {

                throw new Error(
                    "Downloaded image is empty or invalid."
                );

            }


            fs.writeFileSync(
                OUTPUT_PATH,
                buffer
            );


            console.log(
                `📸 Downloaded image: ${OUTPUT_PATH}`
            );

        }

        else {

            throw new Error(
                "Unsupported Puter image response format."
            );

        }


        // ----------------------------------------------------
        // Final validation
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


        if (
            stats.size < 1000
        ) {

            throw new Error(
                "Generated image file is too small."
            );

        }


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
            `Model: ${MODEL}`
        );

        console.log(
            `Quality: ${QUALITY}`
        );

        console.log(
            "Ratio: 9:16"
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
            "Error:",
            error
        );


        if (
            error?.status
        ) {

            console.error(
                `HTTP Status: ${error.status}`
            );

        }


        if (
            error?.message
        ) {

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


        throw error;

    }

}


// ============================================================
// PROCESS ERROR HANDLING
// ============================================================

process.on(
    "unhandledRejection",
    (reason) => {

        console.error(
            "",
            "❌ UNHANDLED PROMISE REJECTION"
        );

        console.error(
            reason
        );

        process.exit(
            1
        );

    }
);


process.on(
    "uncaughtException",
    (error) => {

        console.error(
            "",
            "❌ UNCAUGHT EXCEPTION"
        );

        console.error(
            error
        );

        process.exit(
            1
        );

    }
);


// ============================================================
// RUN
// ============================================================

main()
    .then(
        () => {

            process.exit(
                0
            );

        }
    )
    .catch(
        (error) => {

            console.error(
                "",
                "❌ PUTER GENERATOR FAILED"
            );

            console.error(
                error?.message || error
            );

            process.exit(
                1
            );

        }
    );