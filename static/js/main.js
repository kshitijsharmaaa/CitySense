/**
 * CitySense - Main Client JavaScript
 * Handles component interactivity, dismissible alerts, and UI triggers.
 */

document.addEventListener('DOMContentLoaded', function () {
  console.log('CitySense UI Engine initialized successfully.');

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
});

/** Scrub the landing-page illustration directly from the story's scroll position. */
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
    var sticky = story.querySelector('.cs-story-sticky');
    var worker = story.querySelector('[data-story-worker]');
    var workerPoses = story.querySelectorAll('[data-worker-pose]');
    var pothole = story.querySelector('[data-story-pothole]');
    var patch = story.querySelector('[data-story-patch]');
    var message = story.querySelector('[data-story-message]');
    var caption = story.querySelector('[data-story-caption]');
    var status = story.querySelector('[data-story-status]');
    var steps = Array.prototype.slice.call(story.querySelectorAll('[data-story-step]'));
    var framePending = false;
    var lastCaption = '';
    var lastStep = -1;

    function renderStory() {
      framePending = false;

      if (storySection) {
        storySection.classList.toggle('is-scroll-enhanced', !reducedMotion.matches);
      }
      var progress = 1;
      if (!reducedMotion.matches) {
        var storyTop = window.scrollY + story.getBoundingClientRect().top;
        var scrollRange = Math.max(1, story.offsetHeight - sticky.offsetHeight);
        progress = clamp((window.scrollY - storyTop) / scrollRange, 0, 1);
      }

      // The 3D turnaround character walks into the scene from 20–40% of the
      // scroll track, then changes pose for repair and the finished-road state.
      var walkProgress = smooth((progress - 0.2) / 0.2);
      var workerX = lerp(-350, 360, walkProgress);
      if (progress > 0.86) {
        workerX = lerp(360, 330, smooth((progress - 0.86) / 0.12));
      }

      var repairPose = smooth((progress - 0.47) / 0.12) * (1 - smooth((progress - 0.78) / 0.08));
      var standingPose = smooth((progress - 0.78) / 0.08);
      var walkPose = clamp(1 - repairPose - standingPose, 0, 1);
      var repairStroke = progress >= 0.55 && progress <= 0.82
        ? Math.sin(((progress - 0.55) / 0.27) * Math.PI * 4) * 3
        : 0;
      worker.setAttribute('transform', 'translate(' + workerX.toFixed(2) + ' ' + (58 + repairStroke).toFixed(2) + ')');
      workerPoses.forEach(function (pose) {
        var opacity = pose.dataset.workerPose === 'repair'
          ? repairPose
          : pose.dataset.workerPose === 'standing'
            ? standingPose
            : walkPose;
        pose.setAttribute('opacity', opacity.toFixed(3));
      });

      // Asphalt patch opacity and crater scale are both functions of scroll;
      // there is no timer or independent animation timeline.
      var repair = smooth((progress - 0.55) / 0.31);
      var craterScale = 1 - repair * 0.985;
      pothole.setAttribute(
        'transform',
        'translate(684 438) scale(' + craterScale.toFixed(4) + ') translate(-684 -438)'
      );
      pothole.style.opacity = String(1 - repair);
      patch.style.opacity = String(repair);

      var messageProgress = smooth((progress - 0.84) / 0.14);
      message.style.opacity = String(messageProgress);
      message.style.transform = 'translateY(' + ((1 - messageProgress) * 8).toFixed(2) + 'px)';
      message.setAttribute('aria-hidden', messageProgress < 0.5 ? 'true' : 'false');

      var stepIndex = Math.min(steps.length - 1, Math.floor(progress * steps.length));
      if (stepIndex !== lastStep) {
        steps.forEach(function (step, index) {
          step.classList.toggle('is-active', index === stepIndex);
          step.classList.toggle('is-complete', index < stepIndex);
          if (index === stepIndex) step.setAttribute('aria-current', 'step');
          else step.removeAttribute('aria-current');
        });
        lastStep = stepIndex;
      }

      var captionText;
      if (progress < 0.2) captionText = 'Road hazard reported';
      else if (progress < 0.4) captionText = 'Maintenance team arrives';
      else if (progress < 0.55) captionText = 'Issue assessed and routed';
      else if (progress < 0.86) captionText = 'Pothole repair in progress';
      else captionText = 'Road repaired';

      if (captionText !== lastCaption) {
        caption.textContent = captionText;
        status.textContent = captionText + '. ' + (
          progress >= 0.86
            ? 'From citizen report to real-world resolution.'
            : 'Scroll to follow the response.'
        );
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
