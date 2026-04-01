/* =============================================
   CATHERINE C. HUNT — REALTOR® WEBSITE
   Interactive Behaviors
   ============================================= */

document.addEventListener('DOMContentLoaded', () => {

  // === STICKY HEADER SHADOW ===
  const header = document.getElementById('header');
  window.addEventListener('scroll', () => {
    header.classList.toggle('scrolled', window.scrollY > 20);
  }, { passive: true });


  // === MOBILE NAV ===
  const hamburger = document.getElementById('hamburger');
  const nav = document.getElementById('nav');

  // Create overlay element
  const overlay = document.createElement('div');
  overlay.className = 'nav-overlay';
  document.body.appendChild(overlay);

  function openNav() {
    nav.classList.add('open');
    overlay.classList.add('active');
    hamburger.classList.add('active');
    hamburger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeNav() {
    nav.classList.remove('open');
    overlay.classList.remove('active');
    hamburger.classList.remove('active');
    hamburger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  hamburger.addEventListener('click', () => {
    nav.classList.contains('open') ? closeNav() : openNav();
  });

  overlay.addEventListener('click', closeNav);

  // Close on nav link click (mobile)
  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 900) closeNav();
    });
  });

  // Mobile dropdown toggle
  const navDropdowns = document.querySelectorAll('.nav-dropdown');
  navDropdowns.forEach(dropdown => {
    const trigger = dropdown.querySelector('.nav-link--dropdown');
    trigger.addEventListener('click', (e) => {
      if (window.innerWidth <= 900) {
        e.preventDefault();
        dropdown.classList.toggle('open');
      }
    });
  });

  // Close nav on resize
  window.addEventListener('resize', () => {
    if (window.innerWidth > 900) closeNav();
  });


  // === SMOOTH SCROLL FOR ANCHOR LINKS ===
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      const headerHeight = header.offsetHeight;
      const targetTop = target.getBoundingClientRect().top + window.scrollY - headerHeight - 16;
      window.scrollTo({ top: targetTop, behavior: 'smooth' });
    });
  });


  // === FAQ ACCORDION ===
  const faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(item => {
    const btn = item.querySelector('.faq-question');
    btn.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');
      // Close all
      faqItems.forEach(fi => {
        fi.classList.remove('open');
        fi.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
      });
      // Open clicked if it wasn't open
      if (!isOpen) {
        item.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });


  // === SCROLL ANIMATIONS ===
  const animatedEls = document.querySelectorAll(
    '.stats-grid .stat, .neighborhood-card, .testimonial-card, .bs-card, .faq-item'
  );

  // Add fade-in class
  animatedEls.forEach((el, i) => {
    el.classList.add('fade-in');
    const delay = (i % 4) * 0.1;
    el.style.transitionDelay = `${delay}s`;
  });

  // Also animate section headers
  document.querySelectorAll('.section-title, .about-content, .valuation-content, .contact-info').forEach(el => {
    el.classList.add('fade-in');
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));


  // === FORM SUBMISSIONS ===
  // Valuation form
  const valuationForm = document.getElementById('valuation-form');
  if (valuationForm) {
    valuationForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const btn = valuationForm.querySelector('button[type="submit"]');
      const originalText = btn.textContent;

      // Basic validation
      const required = ['val-address', 'val-name', 'val-phone', 'val-email'];
      let valid = true;
      required.forEach(id => {
        const field = document.getElementById(id);
        if (!field.value.trim()) {
          field.style.borderColor = '#e53e3e';
          valid = false;
          field.addEventListener('input', () => { field.style.borderColor = ''; }, { once: true });
        }
      });

      if (!valid) return;

      btn.textContent = 'Sending…';
      btn.disabled = true;

      // Simulate submission — replace with actual form handler
      setTimeout(() => {
        valuationForm.innerHTML = `
          <div style="text-align:center; padding: 32px 0;">
            <div style="font-size:3rem; margin-bottom:16px;">✓</div>
            <h3 style="font-family:var(--font-serif); color:var(--navy); margin-bottom:12px;">Request Received!</h3>
            <p style="color:var(--text-muted); font-size:0.95rem; line-height:1.7;">
              Thank you! Catherine will be in touch within a few hours with your personalized home valuation.
            </p>
            <p style="color:var(--text-muted); font-size:0.85rem; margin-top:16px;">
              Questions in the meantime? Call <a href="tel:3182680854" style="color:var(--navy); font-weight:600;">(318) 268-0854</a>
            </p>
          </div>
        `;
      }, 1200);
    });
  }

  // Contact form
  const contactForm = document.getElementById('contact-form');
  if (contactForm) {
    contactForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const btn = contactForm.querySelector('button[type="submit"]');
      btn.textContent = 'Sending…';
      btn.disabled = true;

      setTimeout(() => {
        contactForm.innerHTML = `
          <div style="text-align:center; padding: 32px 0;">
            <div style="font-size:3rem; margin-bottom:16px;">✓</div>
            <h3 style="font-family:var(--font-serif); color:var(--navy); margin-bottom:12px;">Message Sent!</h3>
            <p style="color:var(--text-muted); font-size:0.95rem; line-height:1.7;">
              Thanks for reaching out! Catherine typically responds within a few hours.
            </p>
            <p style="color:var(--text-muted); font-size:0.85rem; margin-top:16px;">
              Or call directly: <a href="tel:3182680854" style="color:var(--navy); font-weight:600;">(318) 268-0854</a>
            </p>
          </div>
        `;
      }, 1000);
    });
  }


  // === SEARCH BUTTON (placeholder) ===
  const searchBtn = document.querySelector('.btn--search');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      // Wire to actual IDX search URL when integrating MLS
      const locationInput = document.querySelector('.search-field input');
      const query = locationInput ? locationInput.value.trim() : '';
      const searchUrl = `https://www.forsalebyhunt.com/quick-search${query ? `?location=${encodeURIComponent(query)}` : ''}`;
      window.open(searchUrl, '_blank');
    });
  }

  // === UNSPLASH NEIGHBORHOOD PHOTOS ===
  const UNSPLASH_KEY = '5RdUoM9ShSLFfuaAxXCkjU32sukQYE6jXyMHzUYCLFY';

  // Each card gets a targeted search query for relevant photos
  const neighborhoodQueries = [
    { selector: '.nc-img--minden',      query: 'single family home front yard southern house' },
    { selector: '.nc-img--haughton',    query: 'new construction suburban house brick home' },
    { selector: '.nc-img--waterfront',  query: 'lake house home dock residential waterfront' },
    { selector: '.nc-img--rural',       query: 'farmhouse rural property house acreage' },
    { selector: '.nc-img--sibley',      query: 'charming cottage house small town residential' },
    { selector: '.nc-img--shreveport',  query: 'residential house neighborhood front porch' },
  ];

  neighborhoodQueries.forEach(({ selector, query }) => {
    const el = document.querySelector(selector);
    if (!el) return;

    // Stay on page 1 for highest relevance, pick randomly within top 10 results
    const url = `https://api.unsplash.com/search/photos?query=${encodeURIComponent(query)}&per_page=10&page=1&orientation=landscape&content_filter=high&client_id=${UNSPLASH_KEY}`;

    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (!data.results || data.results.length === 0) return;
        // Pick a random result from the set
        const photo = data.results[Math.floor(Math.random() * data.results.length)];
        const imgUrl = photo.urls.regular; // ~1080px wide, perfect for cards
        el.style.backgroundImage = `url('${imgUrl}')`;
        el.style.backgroundSize = 'cover';
        el.style.backgroundPosition = 'center';
        // Unsplash attribution (required by their API terms)
        el.setAttribute('data-photographer', photo.user.name);
        el.setAttribute('data-photo-link', photo.links.html);
      })
      .catch(() => {
        // Silently fall back to the CSS gradient placeholder if fetch fails
      });
  });


  // Quick search tags
  document.querySelectorAll('.quick-tag').forEach(tag => {
    tag.addEventListener('click', (e) => {
      e.preventDefault();
      const label = tag.textContent.trim();
      // Map tag labels to IDX search URLs — customize these
      const tagMap = {
        'Minden Homes':        'https://www.forsalebyhunt.com/homes-for-sale-in-minden-la',
        'Waterfront':          'https://www.forsalebyhunt.com/quick-search?waterfront=1',
        'Near Barksdale AFB':  'https://www.forsalebyhunt.com/homes-for-sale-in-haughton-la',
        'Under $200K':         'https://www.forsalebyhunt.com/quick-search?max_price=200000',
        'Acreage & Rural':     'https://www.forsalebyhunt.com/quick-search?property_type=land',
        'New Construction':    'https://www.forsalebyhunt.com/quick-search?new_construction=1',
      };
      const url = tagMap[label] || 'https://www.forsalebyhunt.com/quick-search';
      window.open(url, '_blank');
    });
  });

});
