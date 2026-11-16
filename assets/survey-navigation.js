(function(){
  const navbar=document.getElementById('navbar');
  if(!navbar) return;
  function updateNav(){const p=window.scrollY>60;navbar.classList.toggle('nav-transparent',!p);
    navbar.classList.toggle('nav-solid',p);}
  window.addEventListener('scroll',updateNav,{passive:true});updateNav();

  // One index at every width. Without Popover support (or JavaScript),
  // the same links remain visible in normal document flow.
  const surveyMenu=document.getElementById('survey-menu'),
        surveyMenuButton=document.getElementById('survey-menu-button');
  if(surveyMenu&&surveyMenuButton&&'popover' in HTMLElement.prototype){
    surveyMenu.setAttribute('popover','auto');
    navbar.classList.add('survey-nav-enhanced');
    surveyMenuButton.hidden=false;
    function positionSurveyMenu(){
      document.documentElement.style.setProperty('--survey-nav-bottom',navbar.getBoundingClientRect().bottom+'px');
    }
    positionSurveyMenu();
    window.addEventListener('resize',positionSurveyMenu,{passive:true});
    if('ResizeObserver' in window) new ResizeObserver(positionSurveyMenu).observe(navbar);
    surveyMenu.addEventListener('toggle',event=>{
      surveyMenuButton.setAttribute('aria-expanded',String(event.newState==='open'));
    });
    // This is nonmodal navigation: leaving it must reveal the focused page.
    navbar.addEventListener('focusout',event=>{
      if(event.relatedTarget&&!surveyMenu.contains(event.relatedTarget)&&
          event.relatedTarget!==surveyMenuButton&&surveyMenu.matches(':popover-open')){
        surveyMenu.hidePopover();
      }
    });
    surveyMenu.addEventListener('click',event=>{
      const link=event.target.closest('a');
      if(!link||event.defaultPrevented||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey) return;
      surveyMenu.hidePopover();
      if(link.hash&&link.pathname===location.pathname){
        const target=document.getElementById(decodeURIComponent(link.hash.slice(1)));
        if(target){
          target.setAttribute('tabindex','-1');
          target.focus({preventScroll:true});
        }
      }
    });
  }

})();
