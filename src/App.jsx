import { useEffect } from "react";
import { Link } from "react-router-dom";
import AIAssistant from "./components/AIAssistant";
import NavAuth from "./auth/NavAuth";
import "./App.css";

const stepItems = [
  {
    number: "01",
    title: "Search with AI",
    description:
      "Tell our AI assistant your budget, preferred area, and needs. It instantly finds your best-matched properties on an interactive map.",
  },
  {
    number: "02",
    title: "Chat & Negotiate",
    description:
      "Message property owners directly inside bari.com. Discuss rent, facilities, and terms without sharing your personal number.",
  },
  {
    number: "03",
    title: "Book & Move In",
    description:
      "Confirm with secure bKash payment. Optionally book a truck partner for your move - everything done before you arrive at the door.",
  },
];

const featureItems = [
  {
    icon: "AI",
    title: "AI Property Assistant",
    description:
      "Describe your ideal home in plain language. Our AI learns your preferences and surfaces the most relevant matches instantly.",
    featured: true,
  },
  {
    icon: "MAP",
    title: "Interactive Map Search",
    description:
      "Browse properties as pins on a live Google Map. See distance to your university, hospital, bus stop, and market in one view.",
  },
  {
    icon: "SAFE",
    title: "Area Safety Scores",
    description:
      "Every listing shows a community-verified safety rating and proximity data so you can make confident decisions.",
  },
  {
    icon: "CHAT",
    title: "Real-Time Chat",
    description:
      "Talk to property owners directly on the platform. No personal numbers needed - private, fast, and on the record.",
  },
  {
    icon: "MOVE",
    title: "Moving Service",
    description:
      "Book a verified truck or pickup partner right from your booking confirmation. Estimated cost shown before you commit.",
  },
  {
    icon: "PAY",
    title: "Secure bKash Payment",
    description:
      "Pay deposits and short-term bookings via bKash. Fast, trusted, and fully tracked within the platform.",
  },
];

const studentItems = [
  {
    icon: "UNI",
    title: "University-Centric Sublets",
    description:
      "Browse sublets filtered specifically by proximity to your university. See exactly how far each listing is from your campus gate.",
    badge: "BRAC, NSU, DU, BUET, IUB, AIUB, EWU ->",
  },
  {
    icon: "SAFE",
    title: "Secure Housing for Women",
    description:
      "A dedicated, moderated section for female students with owner verification, safety tags, and community reviews.",
    badge: "Admin-verified listings ->",
  },
  {
    icon: "COMM",
    title: "Community Forum",
    description:
      "Ask about neighborhoods, share experiences, post roommate requests, or report unsafe listings - all in one student community.",
    badge: "Join the conversation ->",
  },
  {
    icon: "ROOM",
    title: "Furnished Sublet Options",
    description:
      "Filter for fully furnished rooms - some owners even sell furniture alongside the rental so you arrive and settle in immediately.",
    badge: "Move in the same day ->",
  },
];

function App() {
  useEffect(() => {
    const nav = document.getElementById("mainNav");
    const onScroll = () => {
      if (!nav) {
        return;
      }
      nav.classList.toggle("scrolled", window.scrollY > 60);
    };

    onScroll();
    window.addEventListener("scroll", onScroll);

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const delay = Number(entry.target.getAttribute("data-delay") || 0);
            window.setTimeout(() => {
              entry.target.classList.add("visible");
            }, delay);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 },
    );

    const animatedElements = document.querySelectorAll(
      ".fade-up, .step, .feature-card",
    );

    animatedElements.forEach((element, index) => {
      element.setAttribute("data-delay", String((index % 4) * 100));
      observer.observe(element);
    });

    const featureCards = document.querySelectorAll(".feature-card");
    featureCards.forEach((card, index) => {
      card.style.transitionDelay = `${index * 80}ms`;
    });

    return () => {
      window.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);

  return (
    <>
      <nav id="mainNav">
        <a href="#top" className="nav-logo">
          bari<span>.com</span>
        </a>
        <ul className="nav-links">
          <li>
            <a href="#how">How It Works</a>
          </li>
          <li>
            <a href="#features">Features</a>
          </li>
          <li>
            <a href="#students">Students</a>
          </li>
          <li>
            <Link to="/forum">Community</Link>
          </li>
          <li>
            <a href="#contact">Contact</a>
          </li>
        </ul>
        <div className="nav-right">
          <NavAuth />
          <Link to="/list-property" className="nav-cta">
            List Your Property
          </Link>
        </div>
      </nav>

      <main id="top">
        <section className="hero">
          <div className="hero-fallback" />
          <div className="hero-pattern" />

          <video
            className="hero-video"
            src="/bs.mp4"
            autoPlay
            muted
            loop
            playsInline
          />

          <div className="hero-overlay" />
          <div className="hero-video-softener" />

          <div className="hero-content">
            <div className="hero-eyebrow">
              Bangladesh&apos;s smartest property platform
            </div>
            <h1>
              Find your place
              <br />
              <em>to belong.</em>
            </h1>
            <p className="hero-sub">
              From long-term apartments to student sublets - bari.com connects
              you with verified homes, safety insights, and AI-powered
              recommendations across Bangladesh.
            </p>
            <div className="hero-actions">
              <Link to="/browse" className="btn-primary">
                Explore Properties
              </Link>
              <a href="#how" className="btn-ghost">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle
                    cx="8"
                    cy="8"
                    r="7"
                    stroke="currentColor"
                    strokeWidth="1.2"
                  />
                  <polygon points="6.5,5.5 11,8 6.5,10.5" fill="currentColor" />
                </svg>
                See how it works
              </a>
            </div>
          </div>

          <a className="hero-scroll" href="#stats">
            <span>Scroll</span>
            <div className="scroll-line" />
          </a>
        </section>

        <div className="stats-band" id="stats">
          <div className="stat-item">
            <div className="stat-num">150</div>
            <div className="stat-label">Listings in Dhaka</div>
          </div>
          <div className="stat-item">
            <div className="stat-num">7</div>
            <div className="stat-label">Universities nearby</div>
          </div>
          <div className="stat-item">
            <div className="stat-num">600+</div>
            <div className="stat-label">Safety reviews</div>
          </div>
          <div className="stat-item">
            <div className="stat-num">2</div>
            <div className="stat-label">Languages: English &amp; বাংলা</div>
          </div>
        </div>

        <section className="how-section" id="how">
          <div className="how-grid">
            <div className="how-text">
              <div className="section-tag fade-up">How It Works</div>
              <h2 className="section-title fade-up">
                From search to <em>move-in</em>, all in one place
              </h2>
              <p className="section-body fade-up">
                No more middlemen, no more cold calls. bari.com handles
                everything - finding the right home, chatting with owners,
                booking, and even moving your furniture.
              </p>
              <div className="steps">
                {stepItems.map((step) => (
                  <div className="step" key={step.number}>
                    <div className="step-num">{step.number}</div>
                    <div className="step-content">
                      <h3>{step.title}</h3>
                      <p>{step.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="how-visual">
              <div className="how-visual-bg" />
              <div className="how-visual-pattern" />
              <div className="how-dots" aria-hidden="true">
                {Array.from({ length: 15 }).map((_, index) => (
                  <span key={index} />
                ))}
              </div>
              <div className="how-card">
                <div className="how-card-label">AI Recommendation</div>
                <h4>Merul Badda 2-bed flat, near BRAC University</h4>
                <p>৳22,000/month - Furnished - Safety score 4.4 - 6 min walk to campus</p>
                <div className="how-tags">
                  <span className="how-tag">Women-only</span>
                  <span className="how-tag">Night guard &amp; CCTV</span>
                  <span className="how-tag">Available from January</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="features-section" id="features">
          <div className="features-header">
            <div>
              <div className="section-tag fade-up">Platform Features</div>
              <h2 className="section-title fade-up">
                Everything you need,
                <br />
                <em>nothing you don&apos;t</em>
              </h2>
            </div>
            <p className="section-body fade-up">
              Built specifically for Bangladesh&apos;s rental market, with local
              safety insights, local payment, and local students in mind.
            </p>
          </div>
          <div className="features-grid">
            {featureItems.map((feature) => (
              <div
                className={`feature-card${feature.featured ? " featured" : ""}`}
                key={feature.title}
              >
                <div className="feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="students-section" id="students">
          <div className="fade-up">
            <div className="section-tag">For Students</div>
            <h2 className="section-title">
              Made for students
              <br />
              <em>who are far from home.</em>
            </h2>
            <p className="section-body">
              Whether you&apos;re at BRAC, BUET, NSU, or anywhere else - bari.com
              has dedicated sections to help you find a safe, affordable place
              near your campus.
            </p>
          </div>
          <div className="students-grid">
            {studentItems.map((item) => (
              <div className="student-card" key={item.title}>
                <div className="student-card-icon">{item.icon}</div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <div className="student-badge">{item.badge}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="cta-section" id="contact">
          <div className="section-tag fade-up">Get Started</div>
          <h2 className="section-title fade-up">
            Your next home is
            <br />
            <em>already waiting.</em>
          </h2>
          <p className="section-body fade-up">
            Join thousands of students and families who found their perfect
            match on bari.com. It&apos;s free to search and free to list.
          </p>
          <div className="cta-actions fade-up">
            <Link to="/browse" className="btn-primary">
              Find a Property
            </Link>
            <Link to="/list-property" className="btn-dark">
              List for Free
            </Link>
            <a href="#" className="btn-outline-dark">
              Talk to AI Assistant
            </a>
          </div>
        </section>
      </main>

      <footer>
        <div className="footer-top">
          <div className="footer-brand">
            <a href="#top" className="nav-logo">
              bari<span>.com</span>
            </a>
            <p>
              Bangladesh&apos;s smartest real estate and student sublet platform.
              Find. Chat. Book. Move.
            </p>
          </div>
          <div className="footer-links-group">
            <h4>Platform</h4>
            <ul>
              <li>
                <a href="#">Search Properties</a>
              </li>
              <li>
                <a href="#">List a Property</a>
              </li>
              <li>
                <a href="#">Student Sublets</a>
              </li>
              <li>
                <a href="#">Short-Term Stays</a>
              </li>
            </ul>
          </div>
          <div className="footer-links-group">
            <h4>Company</h4>
            <ul>
              <li>
                <a href="#">About</a>
              </li>
              <li>
                <a href="#">Safety Policy</a>
              </li>
              <li>
                <a href="#">Moving Partners</a>
              </li>
              <li>
                <a href="#">Contact</a>
              </li>
            </ul>
          </div>
          <div className="footer-links-group">
            <h4>Students</h4>
            <ul>
              <li>
                <a href="#">University Guide</a>
              </li>
              <li>
                <a href="#">Women&apos;s Housing</a>
              </li>
              <li>
                <Link to="/forum">Community Forum</Link>
              </li>
              <li>
                <a href="#">Roommate Search</a>
              </li>
            </ul>
          </div>
        </div>
        <div className="footer-bottom">
          <p>&copy; 2026 bari.com - Group 11, CSE471 - BRAC University</p>
          <span>Dhaka, Bangladesh</span>
        </div>
      </footer>
      <AIAssistant />
    </>
  );
}

export default App;
