/*
 * 화면 보조 동작. 이 파일이 없어도 모든 기능은 폼 전송만으로 동작한다.
 *  1) 글자 수 표시
 *  2) 전송 중 표시와 중복 전송 방지 (모델 호출은 토큰을 쓰므로 두 번 보내지 않게 한다)
 *  3) 업로드할 표지 미리보기
 */
(function () {
  'use strict';

  document.querySelectorAll('textarea[maxlength]').forEach(function (area) {
    var counter = document.createElement('span');
    counter.className = 'counter';
    function update() {
      counter.textContent = area.value.length + ' / ' + area.maxLength;
      counter.classList.toggle('is-full', area.value.length >= area.maxLength);
    }
    area.addEventListener('input', update);
    area.insertAdjacentElement('afterend', counter);
    update();
  });

  var busy = document.getElementById('busy');
  document.querySelectorAll('form[data-busy]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (form.dataset.sending) {
        event.preventDefault();
        return;
      }
      form.dataset.sending = '1';
      var button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; }
      if (busy) {
        busy.querySelector('.busy-note').textContent = form.dataset.busy;
        busy.hidden = false;
      }
    });
  });

  // 뒤로 가기로 돌아왔을 때 전송 중 상태가 남지 않도록 되돌린다.
  window.addEventListener('pageshow', function () {
    if (busy) { busy.hidden = true; }
    document.querySelectorAll('form[data-busy]').forEach(function (form) {
      delete form.dataset.sending;
      var button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = false; }
    });
  });

  document.querySelectorAll('.dropzone input[type="file"]').forEach(function (input) {
    var zone = input.closest('.dropzone');
    var preview = zone.querySelector('.dropzone-preview');
    var title = zone.querySelector('strong');
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) { return; }
      title.textContent = file.name;
      if (file.type.indexOf('image/') === 0) {
        preview.src = URL.createObjectURL(file);
        preview.hidden = false;
      }
    });
  });
})();
