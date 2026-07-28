document.addEventListener("htmx:configRequest", (event) => {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    if (token) {
        event.detail.headers["X-CSRFToken"] = token;
    }
});

document.addEventListener("htmx:beforeSwap", (event) => {
    const response = event.detail.xhr;
    if (
        response.status === 400 &&
        response.getResponseHeader("X-Nexus-Swap-Error") === "true"
    ) {
        event.detail.shouldSwap = true;
        event.detail.isError = false;
    }
});
