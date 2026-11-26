const form = document.querySelector("#wl-form")
const status = document.querySelector("#wl-status")
const toast = document.querySelector("#toast")

function showToast(message, kind = "success") {
  if (!toast) return
  toast.textContent = message
  toast.dataset.kind = kind
  toast.classList.add("show")
  setTimeout(() => toast.classList.remove("show"), 3600)
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault()
  status.textContent = "Adding you to the list..."
  try {
    const response = await fetch("/api/briefcase/waitlist", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: document.querySelector("#wl-name").value.trim(),
        email: document.querySelector("#wl-email").value.trim(),
        role: document.querySelector("#wl-role").value.trim() || null,
      }),
    })
    const data = await response.json()
    if (!response.ok) {
      const message = data?.error?.message || "Could not join the waitlist"
      if (response.status === 409) {
        status.textContent = "You are already on the waitlist. We will be in touch."
        showToast("Already registered.", "success")
        return
      }
      throw new Error(message)
    }
    form.reset()
    status.textContent = "You are on the BriefCase early access list. Thank you."
    showToast("Waitlist joined.", "success")
  } catch (error) {
    status.textContent = error.message || "Could not join the waitlist"
    showToast(error.message || "Could not join the waitlist", "error")
  }
})
