export function Footer() {
    // For an example of different footers see: https://getbootstrap.com/docs/5.2/examples/footers/
    return (
        <footer className="d-flex flex-wrap justify-content-between align-items-center mt-4 py-3 border-top">
            <div className="col-md-4 d-flex align-items-center">
                <a href="/" className="mb-3 me-2 mb-md-0 text-muted text-decoration-none lh-1">
                    <img style={{ maxHeight: "2.5rem" }} src=""></img>
                </a>
                <span className="mb-3 mb-md-0 text-muted">TODO: Add logo and project related links</span>
            </div>
            {/* <ul className="nav col-md-4 justify-content-end list-unstyled d-flex">
                <li className="nav-item"><a href="#" className="nav-link px-2 text-muted">Home</a></li>
                <li className="nav-item"><a href="#" className="nav-link px-2 text-muted">Features</a></li>
                <li className="nav-item"><a href="#" className="nav-link px-2 text-muted">Pricing</a></li>
            </ul> */}
        </footer>
    )
}