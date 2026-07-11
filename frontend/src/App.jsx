/**
 * Application shell — gives the React app the same page chrome as the
 * server-rendered site (header, hero, footer) so it reads as a finished page
 * rather than a detached fragment, then mounts the interactive <BrandList />.
 */
import BrandList from "./components/BrandList/BrandList.jsx";

export default function App() {
  return (
    <div className="site">
      <header className="site-header">
        <div className="container">
          <div className="site-title">
            <a href="/">Brand Reviews</a>
          </div>
          <nav className="site-nav" aria-label="Primary">
            <a href="/">Home</a>
            <a href="/api/brands/">API</a>
          </nav>
        </div>
      </header>

      <section className="hero">
        <div className="container">
          <h1>Trusted Brand Reviews</h1>
          <p>
            Compare real customer ratings across industries and find the brands
            you can trust.
          </p>
        </div>
      </section>

      <main className="section">
        <div className="container">
          <BrandList />
        </div>
      </main>

      <footer className="site-footer">
        <div className="container">
          <p>Brand Reviews — a WordPress → Django + React migration demo.</p>
        </div>
      </footer>
    </div>
  );
}
