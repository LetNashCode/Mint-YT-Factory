const fs = require("fs");
const path = require("path");

const {
    init
} = require("@heyputer/puter.js/src/init.cjs");


// ============================================================
// PUTER PRODUCTION IMAGE GENERATOR
// Mint-YT-Factory
//
// Flow:
//
// generate_images.py
//        ↓
// PUTER_IMAGE_PROMPT
//        ↓
// this file
//        ↓
// GPT Image 2
//        ↓ insufficient credits
// GPT Image 1 Mini
//        ↓ insufficient credits
// Gemini image model
//        ↓ insufficient credits
// Grok image model
//
// IMPORTANT:
// This file does NOT contain a hardcoded image prompt.
// The prompt always comes from generate_images.py.
// ============================================================


// ============================================================
// ENVIRONMENT
// ============================================================

const PUTER_AUTH_TOKEN =
    process.env.PUTER_AUTH_TOKEN;

const OUTPUT_PATH =
    process.env.PUTER_OUTPUT_PATH;

const PROMPT =
    process.env.PUTER_IMAGE_PROMPT;

const SEED =
    process.env.PUTER_IMAGE_SEED || "0";

const TIMEOUT_MS = 120000;


// ============================================================
// MODEL FALLBACK CHAIN
// ============================================================
//
// Change the order here if required.
//
// You can also override it using:
//
// PUTER_IMAGE_MODELS="gpt-image-2,gpt-image-1-mini,..."
//
// ============================================================

const DEFAULT_MODELS = [

    "gpt-image-2",

    "gpt-image-1-mini",

    "gemini-2.5-flash-image",

    "grok-imagine-image"

];


const MODELS = (

    process.env.PUTER_IMAGE_MODELS ||

    DEFAULT_MODELS.join(",")

)
    .split(",")

    .map(
        model => model.trim()
    )

    .filter(
        Boolean
    );


// ============================================================
// MODEL OPTIONS
// ============================================================

function getModelOptions(model) {

    // --------------------------------------------------------
    // GPT IMAGE 2
    // --------------------------------------------------------

    if (
        model === "gpt-image-2"
    ) {

        return {

            model: model,

            quality:
                process.env.PUTER_GPT2_QUALITY ||
                "medium",

            ratio: {
                w: 9,
                h: 16
            }

        };

    }


    // --------------------------------------------------------
    // GPT IMAGE 1 MINI
    // --------------------------------------------------------

    if (
        model === "gpt-image-1-mini"
    ) {

        return {

            model: model,

            quality:
                process.env.PUTER_MINI_QUALITY ||
                "low",

            ratio: {
                w: 9,
                h: 16
            }

        };

    }


    // --------------------------------------------------------
    // GEMINI IMAGE
    // --------------------------------------------------------

    if (
        model === "gemini-2.5-flash-image"
    ) {

        return {

            model: model,

            ratio: {
                w: 9,
                h: 16
            }

        };

    }


    // --------------------------------------------------------
    // GROK IMAGE
    // --------------------------------------------------------

    if (
        model === "grok-imagine-image"
    ) {

        return {

            model: model,

            ratio: {
                w: 9,
                h: 16
            }

        };

    }


    // --------------------------------------------------------
    // GENERIC FALLBACK
    // --------------------------------------------------------

    return {

        model: model,

        ratio: {
            w: 9,
            h: 16
        }

    };

}


// ============================================================
// VALIDATION
// ============================================================

function validateEnvironment() {

    if (
        !PUTER_AUTH_TOKEN
    ) {

        throw new Error(
            "PUTER_AUTH_TOKEN is missing."
        );

    }


    if (
        !OUTPUT_PATH
    ) {

        throw new Error(
            "PUTER_OUTPUT_PATH is missing."
        );

    }


    // IMPORTANT:
    // There is intentionally NO fallback prompt.

    if (
        !PROMPT ||
        !PROMPT.trim()
    ) {

        throw new Error(
            "PUTER_IMAGE_PROMPT is missing or empty. " +
            "The image prompt must come from generate_images.py."
        );

    }


    if (
        !MODELS.length
    ) {

        throw new Error(
            "No image models are configured."
        );

    }

}


// ============================================================
// ERROR DESCRIPTION
// ============================================================

function describeError(error) {

    if (!error) {

        return "Unknown error.";

    }


    if (
        typeof error === "string"
    ) {

        return error;

    }


    if (
        error.message
    ) {

        return error.message;

    }


    try {

        return JSON.stringify(
            error
        );

    }
    catch (_) {

        return String(
            error
        );

    }

}


// ============================================================
// CREDIT / QUOTA DETECTION
// ============================================================
//
// Only these types of errors cause a model fallback.
//
// Authentication errors, invalid prompts, SDK errors,
// malformed requests, etc. are NOT silently switched.
// ============================================================

function isCreditError(error) {

    const text = [

        error?.message,

        error?.error?.message,

        error?.error?.code,

        error?.code,

        error?.status,

        error?.statusText

    ]
        .filter(
            Boolean
        )
        .join(" ")
        .toLowerCase();


    const creditPatterns = [

        "insufficient credit",

        "insufficient credits",

        "insufficient balance",

        "insufficient funds",

        "not enough credit",

        "not enough credits",

        "not enough balance",

        "quota exceeded",

        "quota_exceeded",

        "credit limit",

        "credit_limit",

        "usage limit",

        "usage_limit",

        "balance too low",

        "out of credits",

        "credits exhausted",

        "payment required",

        "billing",

        "402"

    ];


    return creditPatterns.some(

        pattern =>
            text.includes(
                pattern
            )

    );

}


// ============================================================
// EXTRACT IMAGE SOURCE
// ============================================================

function extractImageSource(result) {

    if (!result) {

        return null;

    }


    // --------------------------------------------------------
    // Direct string
    // --------------------------------------------------------

    if (
        typeof result === "string"
    ) {

        return result;

    }


    // --------------------------------------------------------
    // Standard Puter response
    // --------------------------------------------------------

    if (
        typeof result.src === "string"
    ) {

        return result.src;

    }


    // --------------------------------------------------------
    // URL response
    // --------------------------------------------------------

    if (
        typeof result.url === "string"
    ) {

        return result.url;

    }


    // --------------------------------------------------------
    // Nested image
    // --------------------------------------------------------

    if (
        result.image &&
        typeof result.image.src === "string"
    ) {

        return result.image.src;

    }


    if (
        result.image &&
        typeof result.image.url === "string"
    ) {

        return result.image.url;

    }


    // --------------------------------------------------------
    // Nested data
    // --------------------------------------------------------

    if (
        result.data &&
        typeof result.data.src === "string"
    ) {

        return result.data.src;

    }


    if (
        result.data &&
        typeof result.data.url === "string"
    ) {

        return result.data.url;

    }


    return null;

}


// ============================================================
// SAVE IMAGE
// ============================================================

async function saveImage(
    imageSource
) {

    if (
        !imageSource
    ) {

        throw new Error(
            "Puter returned no image source."
        );

    }


    // ========================================================
    // DATA URL
    // ========================================================

    if (
        imageSource.startsWith(
            "data:image/"
        )
    ) {

        const commaIndex =
            imageSource.indexOf(
                ","
            );


        if (
            commaIndex === -1
        ) {

            throw new Error(
                "Invalid image data URL returned by Puter."
            );

        }


        const base64Data =
            imageSource.substring(
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


        return buffer.length;

    }


    // ========================================================
    // REMOTE URL
    // ========================================================

    if (

        imageSource.startsWith(
            "http://"
        ) ||

        imageSource.startsWith(
            "https://"
        )

    ) {

        console.log(
            "🌐 Puter returned an image URL."
        );


        const response =
            await fetch(
                imageSource
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
            !buffer ||
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


        return buffer.length;

    }


    throw new Error(
        "Unsupported Puter image response format."
    );

}


// ============================================================
// GENERATE WITH ONE MODEL
// ============================================================

async function generateWithModel(
    puter,
    model
) {

    const options =
        getModelOptions(
            model
        );


    console.log("");

    console.log(
        `🧠 Trying model: ${model}`
    );

    console.log(
        `Options: ${JSON.stringify(options)}`
    );


    const startTime =
        Date.now();


    // --------------------------------------------------------
    // Send request
    // --------------------------------------------------------

    const generationPromise =
        puter.ai.txt2img(

            PROMPT,

            options

        );


    // --------------------------------------------------------
    // Timeout
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Wait for Puter
    // --------------------------------------------------------

    const result =
        await Promise.race(

            [

                generationPromise,

                timeoutPromise

            ]

        );


    const elapsed =
        (

            (
                Date.now() -
                startTime
            )
            /
            1000

        ).toFixed(1);


    console.log(
        `✅ ${model} generation completed after ${elapsed}s.`
    );


    // --------------------------------------------------------
    // Response diagnostics
    // --------------------------------------------------------

    console.log(
        "Response type:",
        typeof result
    );


    if (

        typeof result === "object" &&

        result !== null

    ) {

        console.log(
            "Response keys:",
            Object.keys(
                result
            ).join(", ")
        );

    }


    // --------------------------------------------------------
    // Extract image
    // --------------------------------------------------------

    const imageSource =
        extractImageSource(
            result
        );


    if (
        !imageSource
    ) {

        throw new Error(
            `${model} completed but no image source was returned.`
        );

    }


    // --------------------------------------------------------
    // Save
    // --------------------------------------------------------

    const bytes =
        await saveImage(
            imageSource
        );


    return {

        model: model,

        bytes: bytes,

        elapsed: elapsed

    };

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
        `Prompt length: ${PROMPT.length}`
    );


    console.log(
        `Prompt: ${PROMPT}`
    );


    console.log(
        `Output: ${OUTPUT_PATH}`
    );


    console.log(
        `Seed: ${SEED}`
    );


    console.log(
        "Ratio: 9:16"
    );


    console.log(
        `Fallback chain: ${MODELS.join(" → ")}`
    );


    // ========================================================
    // OUTPUT DIRECTORY
    // ========================================================

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


    // ========================================================
    // REMOVE OLD OUTPUT
    // ========================================================

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


    // ========================================================
    // INITIALIZE PUTER
    // ========================================================

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
                describeError(
                    error
                )
            }`

        );

    }


    if (
        !puter
    ) {

        throw new Error(
            "Puter initialization returned an empty client."
        );

    }


    console.log(
        "✅ Puter initialized successfully."
    );


    // ========================================================
    // MODEL FALLBACK LOOP
    // ========================================================

    printHeader(
        "🧠 STARTING MODEL FALLBACK CHAIN"
    );


    let lastError =
        null;


    for (

        let modelIndex = 0;

        modelIndex < MODELS.length;

        modelIndex++

    ) {

        const model =
            MODELS[
                modelIndex
            ];


        console.log("");

        console.log(
            `MODEL ${
                modelIndex + 1
            }/${MODELS.length}: ${model}`
        );


        try {

            const result =
                await generateWithModel(

                    puter,

                    model

                );


            // ------------------------------------------------
            // Validate output
            // ------------------------------------------------

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


            // =================================================
            // SUCCESS
            // =================================================

            printHeader(
                "🎉 PUTER IMAGE GENERATION SUCCESSFUL"
            );


            console.log(
                `Model used: ${result.model}`
            );


            console.log(
                `File: ${OUTPUT_PATH}`
            );


            console.log(
                `Size: ${result.bytes} bytes`
            );


            console.log(
                `Generation time: ${result.elapsed} seconds`
            );


            console.log(
                `Models attempted: ${
                    modelIndex + 1
                }`
            );


            if (
                modelIndex > 0
            ) {

                console.log(
                    "⚡ FALLBACK MODEL USED"
                );

            }


            printHeader(
                "✅ IMAGE COMPLETE"
            );


            return;

        }
        catch (error) {

            lastError =
                error;


            const message =
                describeError(
                    error
                );


            console.error("");

            console.error(
                `❌ ${model} failed.`
            );


            console.error(
                `Reason: ${message}`
            );


            // =================================================
            // CREDIT / QUOTA ERROR
            // =================================================

            if (
                isCreditError(
                    error
                )
            ) {

                console.log("");

                console.log(
                    `💳 ${model} appears to have insufficient credits/quota.`
                );


                if (

                    modelIndex + 1 < MODELS.length

                ) {

                    const nextModel =
                        MODELS[
                            modelIndex + 1
                        ];


                    console.log(
                        `➡️ Switching to ${nextModel}`
                    );


                    continue;

                }


                console.log(
                    "❌ No more fallback models available."
                );


                break;

            }


            // =================================================
            // OTHER ERROR
            // =================================================
            //
            // Do NOT silently switch models.
            //
            // This prevents authentication errors,
            // invalid prompts, malformed requests, SDK
            // errors, etc. from being hidden.
            // =================================================

            console.error("");

            console.error(
                "🛑 This does not look like a credit/quota error."
            );


            console.error(
                "The pipeline will stop so the real error can be fixed."
            );


            throw error;

        }

    }


    // ========================================================
    // EVERYTHING FAILED
    // ========================================================

    printHeader(
        "❌ ALL PUTER IMAGE MODELS FAILED"
    );


    throw new Error(

        `All configured image models failed. Last error: ${
            describeError(
                lastError
            )
        }`

    );

}


// ============================================================
// PROCESS ERROR HANDLERS
// ============================================================

process.on(

    "unhandledRejection",

    (reason) => {

        console.error("");

        console.error(
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

        console.error("");

        console.error(
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

            console.error("");

            console.error(
                "❌ PUTER GENERATOR FAILED"
            );


            console.error(
                describeError(
                    error
                )
            );


            process.exit(
                1
            );

        }

    );