const BASE_URL = "http://localhost:8000/api/v1"

export async function apiFetch(
    path: string,
    method: string = "GET",
    body?: any,
    useSample: boolean = false
) {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };

    if (useSample) {
        headers["X-Use-Sample"] = "true";
    }

    const response = await fetch(`${BASE_URL}${path}`, {
        method, headers,
        body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
        const err = new Error(`API Error: ${response.statusText}`) as Error & { status?: number };
        err.status = response.status;
        throw err;
    }

    return response.json();
}