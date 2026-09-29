/**
 * CitySense - Main Client JavaScript
 * Handles component interactivity, dismissible alerts, and UI triggers.
 */

document.addEventListener('DOMContentLoaded', function () {
  console.log('CitySense UI Engine initialized successfully.');

  initializeLayoutPreviewToggle();

  // Initialize Bootstrap Tooltips if present
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Auto-dismiss alert notifications after 5 seconds if marked with auto-dismiss class
  var autoDismissAlerts = document.querySelectorAll('.cs-alert-autodismiss');
  autoDismissAlerts.forEach(function (alertEl) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
      if (bsAlert) {
        bsAlert.close();
      }
    }, 5000);
  });

  initializeScrollStories();
  initializeProcessReveal();
  initializeLivingCityParallax();
});

/** Add a small pointer response to auth ambience without moving the form card. */
function initializeLivingCityParallax() {
  var scene = document.querySelector('.cs-living-city--auth');
  if (!scene) return;

  var finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!finePointer.matches || reducedMotion.matches) return;

  var framePending = false;
  var pointerX = 0;
  var pointerY = 0;
  function updateParallax() {
    framePending = false;
    scene.style.setProperty('--cs-city-parallax-x', pointerX + 'px');
    scene.style.setProperty('--cs-city-parallax-y', pointerY + 'px');
    scene.style.setProperty('--cs-city-parallax-soft-x', (pointerX * -.45) + 'px');
    scene.style.setProperty('--cs-city-parallax-soft-y', (pointerY * -.45) + 'px');
    scene.style.setProperty('--cs-city-parallax-aura-x', (pointerX * .25) + 'px');
    scene.style.setProperty('--cs-city-parallax-aura-y', (pointerY * .25) + 'px');
  }
  function queueParallax(x, y) {
    pointerX = x;
    pointerY = y;
    if (framePending) return;
    framePending = true;
    window.requestAnimationFrame(updateParallax);
  }

  window.addEventListener('pointermove', function (event) {
    queueParallax((event.clientX / window.innerWidth - .5) * 22,
      (event.clientY / window.innerHeight - .5) * 16);
  }, { passive: true });
  document.documentElement.addEventListener('pointerleave', function () { queueParallax(0, 0); });
}
/** Let mobile demo viewers switch between responsive and desktop-width layouts. */
function initializeLayoutPreviewToggle() {
  var buttons = document.querySelectorAll('[data-preview-toggle]');
  var viewport = document.getElementById('cs-viewport');
  if (!buttons.length || !viewport) return;

  var storageKey = 'citysense-layout-preview';
  var isDesktopPreview = document.documentElement.classList.contains('cs-desktop-preview');
  var isEmbeddedPreview = false;
  try {
    isEmbeddedPreview = window.self !== window.top;
  } catch (error) {
    isEmbeddedPreview = true;
  }
  if (isEmbeddedPreview) document.documentElement.classList.add('cs-preview-embedded');

  function renderButton() {
    buttons.forEach(function (button) {
      var mobileControl = button.classList.contains('cs-preview-toggle-mobile');
      var label = mobileControl ? (isDesktopPreview ? 'Mobile' : 'Desktop') : 'Mobile view';
      button.setAttribute('aria-pressed', String(isDesktopPreview));
      button.setAttribute('aria-label', isDesktopPreview ? 'Switch to mobile view' : 'Switch to desktop view');
      button.classList.toggle('is-active', isDesktopPreview);
      var labelNode = button.querySelector('.cs-preview-label');
      if (labelNode) labelNode.textContent = label;
    });
  }

  renderButton();
  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      if (window.innerWidth >= 992 && !isEmbeddedPreview) {
        openDesktopMobilePreview();
        buttons.forEach(function (control) {
          control.setAttribute('aria-pressed', 'true');
          control.classList.add('is-active');
        });
        return;
      }

      isDesktopPreview = !isDesktopPreview;
      document.documentElement.classList.toggle('cs-desktop-preview', isDesktopPreview);
      viewport.setAttribute('content', isDesktopPreview
        ? 'width=1280, initial-scale=0.3'
        : 'width=device-width, initial-scale=1.0');
      try {
        sessionStorage.setItem(storageKey, isDesktopPreview ? 'desktop' : 'mobile');
      } catch (error) {
        // The switch still works for this page if storage is unavailable.
      }
      renderButton();
      window.scrollTo(0, 0);
    });
  });

  function openDesktopMobilePreview() {
    if (document.querySelector('.cs-device-preview-overlay')) return;

    var previewUrl = new URL(window.location.href);
    previewUrl.searchParams.set('cs_preview', 'mobile');
    var overlay = document.createElement('div');
    overlay.className = 'cs-device-preview-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Mobile layout preview');
    overlay.innerHTML = '<section class="cs-device-preview-frame">' +
      '<header class="cs-device-preview-toolbar"><span><i class="bi bi-phone me-2" aria-hidden="true"></i>Mobile preview</span>' +
      '<button type="button" class="cs-device-preview-close"><span class="cs-preview-switch is-active" aria-hidden="true"><span></span></span><span>Desktop view</span></button></header>' +
      '<iframe title="CitySense mobile layout" loading="eager"></iframe></section>';

    var iframe = overlay.querySelector('iframe');
    iframe.src = previewUrl.toString();
    document.body.appendChild(overlay);
    document.body.classList.add('cs-preview-open');

    function closePreview() {
      overlay.remove();
      document.body.classList.remove('cs-preview-open');
      buttons.forEach(function (control) {
        control.setAttribute('aria-pressed', 'false');
        control.classList.remove('is-active');
      });
      var visibleControl = Array.prototype.find.call(buttons, function (control) {
        return control.offsetParent !== null;
      });
      if (visibleControl) visibleControl.focus();
      document.removeEventListener('keydown', onKeyDown);
    }
    function onKeyDown(event) {
      if (event.key === 'Escape') closePreview();
    }

    overlay.querySelector('.cs-device-preview-close').addEventListener('click', closePreview);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) closePreview();
    });
    document.addEventListener('keydown', onKeyDown);
    overlay.querySelector('.cs-device-preview-close').focus();
  }
}

/** Reveal the editorial process sequence once it enters the viewport. */
function initializeProcessReveal() {
  var processList = document.querySelector('[data-process-list]');
  if (!processList) return;

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (reducedMotion.matches || !('IntersectionObserver' in window)) {
    processList.classList.add('is-visible');
    return;
  }

  processList.classList.add('is-observe');
  var observer = new IntersectionObserver(function (entries) {
    if (!entries.some(function (entry) { return entry.isIntersecting; })) return;
    processList.classList.add('is-visible');
    observer.unobserve(processList);
  }, { threshold: 0.12 });
  observer.observe(processList);
}

/** Scrub the complete hero-to-road story directly from the page scroll position. */
function initializeScrollStories() {
  var stories = document.querySelectorAll('[data-scroll-story]');
  if (!stories.length) return;

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var clamp = function (value, min, max) { return Math.min(max, Math.max(min, value)); };
  var smooth = function (value) {
    var t = clamp(value, 0, 1);
    return t * t * (3 - 2 * t);
  };
  var lerp = function (start, end, amount) { return start + (end - start) * amount; };

  stories.forEach(function (story) {
    if (story.dataset.scrollStoryInitialized === 'true') return;
    story.dataset.scrollStoryInitialized = 'true';

    var storySection = story.closest('.cs-scroll-story');
    var stage = story.querySelector('.cs-story-stage');
    var hero = story.querySelector('[data-story-hero-layer]');
    var road = story.querySelector('[data-story-road]');
    var roadArt = story.querySelector('[data-story-road-art]');
    var avatar = story.querySelector('[data-story-avatar]');
    var heroPoses = story.querySelectorAll('[data-hero-pose]');
    var worker = story.querySelector('[data-story-worker]');
    var workerPoses = story.querySelectorAll('[data-worker-pose]');
    var pothole = story.querySelector('[data-story-pothole]');
    var patch = story.querySelector('[data-story-patch]');
    var message = story.querySelector('[data-story-message]');
    var caption = story.querySelector('[data-story-caption]');
    var status = story.querySelector('[data-story-status]');
    var framePending = false;
    var lastCaption = '';

    function renderStory() {
      framePending = false;

      if (storySection) {
        storySection.classList.toggle('is-scroll-enhanced', !reducedMotion.matches);
      }
      var progress = 1;
      if (!reducedMotion.matches) {
        var storyTop = window.scrollY + story.getBoundingClientRect().top;
        var scrollRange = Math.max(1, story.offsetHeight - stage.offsetHeight);
        progress = clamp((window.scrollY - storyTop) / scrollRange, 0, 1);
      }

      var stageWidth = stage.clientWidth;
      var stageHeight = stage.clientHeight;
      var mobile = stageWidth < 768;
      var compact = stageWidth < 992;
      var heroHeight = Math.min(
        stageHeight * (mobile ? 0.38 : compact ? 0.46 : 0.8),
        stageWidth * (mobile ? 0.58 : compact ? 0.68 : 1.0)
      );
      var heroWidth = heroHeight * (2 / 3);
      var heroCenterX = stageWidth * (mobile ? 0.8 : compact ? 0.77 : 0.78);
      var heroLeft = heroCenterX - heroWidth / 2;
      var heroTop = stageHeight - heroHeight - stageHeight * 0.02;

      // The road art retains its original 1000 × 560 composition. Its worker
      // landing point uses those same SVG coordinates at every viewport size.
      var roadScale = stageWidth / 1000;
      var roadHeight = roadScale * 560;
      var roadTop = stageHeight - roadHeight;
      var landingScale = mobile ? 1.1 : 1;
      var repairSceneScale = landingScale * 0.7;
      var repairScaleProgress = smooth((progress - 0.55) / 0.14);
      var workerScale = lerp(landingScale, repairSceneScale, repairScaleProgress);
      var landingWidth = 320 * roadScale * landingScale;
      var landingHeight = 480 * roadScale * landingScale;
      var landingLeft = (520 * roadScale) - landingWidth / 2;
      var landingTop = roadTop + (58 + 480 - 480 * landingScale) * roadScale;

      // 0.20–0.30: prepare. Crossed arms give way to the referenced jump pose.
      var prepare = smooth((progress - 0.2) / 0.1);
      var crossedOpacity = 1 - smooth((progress - 0.27) / 0.06);
      var jumpPoseOpacity = smooth((progress - 0.27) / 0.06);
      heroPoses.forEach(function (pose) {
        pose.style.opacity = pose.dataset.heroPose === 'jump'
          ? String(jumpPoseOpacity)
          : String(crossedOpacity);
      });

      var avatarLeft = heroLeft;
      var avatarTop = heroTop + prepare * 16;
      var avatarWidth = heroWidth;
      var avatarHeight = heroHeight * (1 - prepare * 0.035);

      // 0.30–0.45: fly diagonally toward the road; 0.45–0.55: land as the
      // existing pothole scene moves into place behind the same character.
      if (progress >= 0.3 && progress < 0.45) {
        var jumpProgress = smooth((progress - 0.3) / 0.15);
        avatarLeft = lerp(heroLeft, landingLeft, jumpProgress);
        avatarTop = lerp(heroTop + 16, stageHeight * 0.07, jumpProgress);
        avatarWidth = lerp(heroWidth, landingWidth, jumpProgress);
        avatarHeight = lerp(heroHeight, landingHeight, jumpProgress);
      } else if (progress >= 0.45) {
        var landingProgress = smooth((progress - 0.45) / 0.1);
        avatarLeft = landingLeft;
        avatarWidth = landingWidth;
        avatarHeight = landingHeight;
        avatarTop = lerp(stageHeight * 0.07, landingTop, landingProgress);
      }

      var jumpFade = 1 - smooth((progress - 0.5) / 0.05);
      avatar.style.left = avatarLeft.toFixed(2) + 'px';
      avatar.style.top = avatarTop.toFixed(2) + 'px';
      avatar.style.width = avatarWidth.toFixed(2) + 'px';
      avatar.style.height = avatarHeight.toFixed(2) + 'px';
      avatar.style.opacity = String(Math.max(crossedOpacity, jumpPoseOpacity) * jumpFade);

      var heroProgress = smooth((progress - 0.44) / 0.11);
      hero.style.opacity = String(1 - heroProgress);
      hero.style.transform = 'translateY(' + (-24 * heroProgress).toFixed(2) + 'px)';
      var roadProgressIn = smooth((progress - 0.44) / 0.11);
      road.style.opacity = String(roadProgressIn);
      roadArt.style.transform = 'scale(' + (1.08 - roadProgressIn * 0.08).toFixed(3) + ')';

      var landingBlend = smooth((progress - 0.51) / 0.04);
      worker.style.opacity = String(landingBlend);
      var workerX = 360;
      worker.setAttribute(
        'transform',
        'translate(' + workerX + ' 58) translate(160 480) scale(' + workerScale + ') translate(-160 -480)'
      );

      // The road-repair timeline is the existing pothole/patch behavior mapped
      // into the final 45% of this single continuous scroll range.
      var roadProgress = clamp((progress - 0.55) / 0.45, 0, 1);
      var repairPose = smooth((roadProgress - 0.22) / 0.12) * (1 - smooth((roadProgress - 0.78) / 0.1));
      var standingPose = smooth((roadProgress - 0.84) / 0.12);
      var walkPose = clamp(1 - repairPose - standingPose, 0, 1);
      var repairStroke = roadProgress >= 0.22 && roadProgress <= 0.84
        ? Math.sin(((roadProgress - 0.22) / 0.62) * Math.PI * 4) * 3
        : 0;
      worker.setAttribute(
        'transform',
        'translate(' + workerX + ' ' + (58 + repairStroke).toFixed(2) + ') translate(160 480) scale(' + workerScale + ') translate(-160 -480)'
      );
      workerPoses.forEach(function (pose) {
        var opacity = pose.dataset.workerPose === 'repair'
          ? repairPose
          : pose.dataset.workerPose === 'standing'
            ? standingPose
            : walkPose;
        pose.setAttribute('opacity', opacity.toFixed(3));
      });

      var repair = smooth((roadProgress - 0.22) / 0.67);
      var craterScale = 1 - repair * 0.985;
      pothole.setAttribute(
        'transform',
        'translate(684 438) scale(' + craterScale.toFixed(4) + ') translate(-684 -438)'
      );
      pothole.style.opacity = String(1 - repair);
      patch.style.opacity = String(repair);

      var messageProgress = smooth((progress - 0.94) / 0.06);
      message.style.opacity = String(messageProgress);
      message.style.transform = 'translateY(' + ((1 - messageProgress) * 12).toFixed(2) + 'px)';
      message.setAttribute('aria-hidden', messageProgress < 0.5 ? 'true' : 'false');

      var captionText;
      if (progress < 0.2) captionText = 'Meet the CitySense worker';
      else if (progress < 0.3) captionText = 'Getting ready to jump';
      else if (progress < 0.45) captionText = 'Jumping into action';
      else if (progress < 0.55) captionText = 'Landing beside the pothole';
      else if (progress < 0.65) captionText = 'Preparing the repair';
      else if (progress < 0.95) captionText = 'Repairing the road';
      else captionText = 'Road repaired';

      if (captionText !== lastCaption) {
        caption.textContent = captionText;
        status.textContent = captionText + (progress >= 0.95
          ? '. From citizen report to real-world resolution.'
          : '. Scroll to follow the story.');
        lastCaption = captionText;
      }
    }

    function requestRender() {
      if (framePending) return;
      framePending = true;
      window.requestAnimationFrame(renderStory);
    }

    window.addEventListener('scroll', requestRender, { passive: true });
    window.addEventListener('resize', requestRender, { passive: true });
    if (typeof reducedMotion.addEventListener === 'function') {
      reducedMotion.addEventListener('change', requestRender);
    } else if (typeof reducedMotion.addListener === 'function') {
      reducedMotion.addListener(requestRender);
    }
    requestRender();
  });
}
