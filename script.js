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
  // Leads are delivered via FormSubmit.co — no account needed. The FIRST
  // submission triggers a one-time activation email to LEAD_EMAIL that must
  // be confirmed before deliveries start.
  const LEAD_EMAIL = 'forsalebyhunt@gmail.com';

  function sendLead(fields) {
    return fetch(`https://formsubmit.co/ajax/${LEAD_EMAIL}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(fields),
    }).then(r => {
      if (!r.ok) throw new Error(`FormSubmit ${r.status}`);
      return r.json();
    });
  }

  function showFormError(form, btn, originalText) {
    btn.textContent = originalText;
    btn.disabled = false;
    let err = form.querySelector('.form-error');
    if (!err) {
      err = document.createElement('p');
      err.className = 'form-error';
      err.style.cssText = 'color:#e53e3e; font-size:0.9rem; margin-top:12px; text-align:center;';
      btn.insertAdjacentElement('afterend', err);
    }
    err.innerHTML = 'Something went wrong sending your message. Please try again, or call <a href="tel:3182680854">(318) 268-0854</a>.';
  }

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

      sendLead({
        _subject: 'New Home Valuation Request — forsalebyhunt',
        form: 'Home Valuation',
        address: document.getElementById('val-address').value.trim(),
        name: document.getElementById('val-name').value.trim(),
        phone: document.getElementById('val-phone').value.trim(),
        email: document.getElementById('val-email').value.trim(),
        timeline: document.getElementById('val-timeline').value,
      }).then(() => {
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
      }).catch(() => showFormError(valuationForm, btn, originalText));
    });
  }

  // Contact form
  const contactForm = document.getElementById('contact-form');
  if (contactForm) {
    contactForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const btn = contactForm.querySelector('button[type="submit"]');
      const originalText = btn.textContent;
      btn.textContent = 'Sending…';
      btn.disabled = true;

      sendLead({
        _subject: 'New Website Contact — forsalebyhunt',
        form: 'Contact',
        name: `${document.getElementById('c-name').value.trim()} ${document.getElementById('c-last').value.trim()}`.trim(),
        email: document.getElementById('c-email').value.trim(),
        phone: document.getElementById('c-phone').value.trim(),
        interest: document.getElementById('c-interest').value,
        message: document.getElementById('c-message').value.trim(),
      }).then(() => {
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
      }).catch(() => showFormError(contactForm, btn, originalText));
    });
  }


  // === SEARCH BUTTON ===
  // Builds a Zillow search from the form fields. Swap for IDX search when
  // MLS/IDX access is available.
  const searchBtn = document.querySelector('.btn--search');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const locationInput = document.querySelector('.search-field input');
      const selects = document.querySelectorAll('.search-row select');
      const query = (locationInput && locationInput.value.trim()) || 'Minden, LA';
      const parsePrice = v => Number(v.replace(/[^0-9]/g, '')) || null;
      const filterState = {};
      const minPrice = selects[0] && parsePrice(selects[0].value);
      const maxPrice = selects[1] && parsePrice(selects[1].value);
      const minBeds = selects[2] && parseInt(selects[2].value, 10);
      if (minPrice || maxPrice) filterState.price = { ...(minPrice && { min: minPrice }), ...(maxPrice && { max: maxPrice }) };
      if (minBeds) filterState.beds = { min: minBeds };
      const state = { usersSearchTerm: query, filterState };
      const searchUrl = `https://www.zillow.com/homes/for_sale/?searchQueryState=${encodeURIComponent(JSON.stringify(state))}`;
      window.open(searchUrl, '_blank');
    });
  }

  // Quick search tags
  document.querySelectorAll('.quick-tag').forEach(tag => {
    tag.addEventListener('click', (e) => {
      e.preventDefault();
      const label = tag.textContent.trim();
      // Portal searches for now — swap to IDX search when MLS access is available
      const tagMap = {
        'Minden Homes':        'https://www.zillow.com/minden-la/',
        'Waterfront':          'https://www.realtor.com/realestateandhomes-search/Homer_LA/with_waterfront',
        'Near Barksdale AFB':  'https://www.zillow.com/haughton-la/',
        'Under $200K':         'https://www.realtor.com/realestateandhomes-search/Minden_LA/price-na-200000',
        'Acreage & Rural':     'https://www.realtor.com/realestateandhomes-search/Minden_LA/type-land',
        'New Construction':    'https://www.zillow.com/bossier-city-la/new-homes/',
      };
      const url = tagMap[label] || 'https://www.zillow.com/minden-la/';
      window.open(url, '_blank');
    });
  });

});
