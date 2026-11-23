from fastapi import Request

@app.api_route("/chat", methods=["GET", "POST"])
def chat(request: Request):
    if request.method == "POST":
        # handle POST
        return {"message": "POST request"}
    else:
        # handle GET
        return {"message": "GET request - use /docs to POST"}