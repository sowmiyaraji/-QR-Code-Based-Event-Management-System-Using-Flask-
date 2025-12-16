// Confirm logout
document.addEventListener("DOMContentLoaded", () => {
    const logout = document.querySelector(".logout");

    if (logout) {
        logout.addEventListener("click", (e) => {
            if (!confirm("Are you sure you want to logout?")) {
                e.preventDefault();
            }
        });
    }
});
