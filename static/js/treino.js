/* ===== Montador de treinos (treino.html) ===== */
(function () {
  "use strict";
  var ALUNO_ID = document.getElementById ? null : null;

  function alunoId() {
    var m = window.location.pathname.match(/\/aluno\/(\d+)\/treino/);
    return m ? parseInt(m[1], 10) : null;
  }

  function buscar(ex, termo, alvo) {
    var url = "/exercicios/buscar?q=" + encodeURIComponent(termo || "");
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var itens = (d && d.itens) || [];
        ex.innerHTML = "";
        if (!itens.length) {
          ex.innerHTML = '<div class="sem-resultado muted small">Nenhum exercício encontrado. Tente outro termo.</div>';
          return;
        }
        itens.forEach(function (x) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "lib-item";
          var nome = document.createElement("div");
          nome.className = "strong";
          nome.textContent = x.nome;
          var meta = document.createElement("div");
          meta.className = "muted small";
          meta.textContent = [x.grupo, x.padrao, x.equipamento, x.nivel].filter(Boolean).join(" · ");
          btn.appendChild(nome);
          btn.appendChild(meta);
          btn.addEventListener("click", function () { alvo(x); });
          ex.appendChild(btn);
        });
      });
  }

  function post(url, formData) {
    return fetch(url, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    });
  }

  /* --- Busca na biblioteca para adicionar exercício --- */
  document.querySelectorAll(".busca-lib").forEach(function (input) {
    var treinoId = input.getAttribute("data-treino-id");
    var box = document.querySelector('.busca-lib-results[data-treino-id="' + treinoId + '"]');
    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        buscar(box, input.value, function (x) {
          var fd = new FormData();
          fd.append("ex_id", x.id);
          box.innerHTML = "";
          post("/treino/" + treinoId + "/exercicio/padrao", fd)
            .then(function () { window.location.reload(); });
        });
      }, 200);
    });
  });

  /* --- Substituir exercício --- */
  var exercicioAtual = null;
  function abrirSubstituicao(exercicioId) {
    exercicioAtual = exercicioId;
    var d = document.getElementById("form-substituir");
    var box = d.querySelector(".busca-subst-results");
    box.innerHTML = "";
    d.querySelector(".busca-subst").value = "";
    d.showModal();
    buscar(box, "", function (x) {
      var fd = new FormData();
      fd.append("ex_id", x.id);
      box.innerHTML = "";
      post("/exercicio/" + exercicioAtual + "/substituir", fd)
        .then(function () { window.location.reload(); });
    });
  }
  window.abrirSubstituicao = abrirSubstituicao;

  var buscaSubst = document.querySelector(".busca-subst");
  if (buscaSubst) {
    var timerS = null;
    buscaSubst.addEventListener("input", function () {
      clearTimeout(timerS);
      timerS = setTimeout(function () {
        var box = document.querySelector(".busca-subst-results");
        buscar(box, buscaSubst.value, function (x) {
          var fd = new FormData();
          fd.append("ex_id", x.id);
          box.innerHTML = "";
          post("/exercicio/" + exercicioAtual + "/substituir", fd)
            .then(function () { window.location.reload(); });
        });
      }, 200);
    });
  }

  /* --- Drag and drop para reordenar --- */
  function ligarDnD(tabela) {
    var linhas = Array.prototype.slice.call(tabela.querySelectorAll("tbody tr[data-ex-id]"));
    linhas.forEach(function (linha) {
      linha.addEventListener("dragstart", function (e) {
        e.dataTransfer.setData("text/plain", linha.getAttribute("data-ex-id"));
        linha.classList.add("arrastando");
      });
      linha.addEventListener("dragend", function () {
        linha.classList.remove("arrastando");
        document.querySelectorAll(".ordem-lista tbody tr").forEach(function (r) {
          r.classList.remove("drag-over");
        });
        salvarOrdem(tabela);
      });
      linha.addEventListener("dragover", function (e) {
        e.preventDefault();
        var arrastada = tabela.querySelector("tr.arrastando");
        if (arrastada && arrastada !== linha) {
          var todas = Array.prototype.slice.call(tabela.querySelectorAll("tbody tr[data-ex-id]"));
          var posA = todas.indexOf(arrastada);
          var posB = todas.indexOf(linha);
          if (posA < posB) {
            tabela.querySelector("tbody").insertBefore(arrastada, linha.nextSibling);
          } else {
            tabela.querySelector("tbody").insertBefore(arrastada, linha);
          }
        }
      });
    });
  }

  function salvarOrdem(tabela) {
    var treinoId = tabela.getAttribute("data-treino-id");
    var ids = Array.prototype.map.call(
      tabela.querySelectorAll("tbody tr[data-ex-id]"),
      function (r) { return parseInt(r.getAttribute("data-ex-id"), 10); }
    );
    fetch("/treino/" + treinoId + "/exercicios/ordem", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids }),
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) {
          tabela.querySelectorAll("tbody tr").forEach(function (r, i) {
            r.querySelector(".ordem-handle").textContent = String(i + 1);
          });
        }
      });
  }

  document.querySelectorAll("table.ordem-lista").forEach(ligarDnD);

  /* --- Modal novo treino: em branco vs modelo --- */
  function alternarModoTreino(modo) {
    var manual = document.getElementById("modo-manual");
    var modelo = document.getElementById("modo-modelo");
    var btnManual = document.getElementById("btn-modo-manual");
    var btnModelo = document.getElementById("btn-modo-modelo");
    manual.style.display = modo === "manual" ? "" : "none";
    modelo.style.display = modo === "modelo" ? "" : "none";
    btnManual.classList.toggle("primary", modo === "manual");
    btnModelo.classList.toggle("primary", modo === "modelo");
    var form = document.getElementById("form-novo-treino-action");
    var alvo = "/aluno/" + alunoId() + "/treino/" + (modo === "modelo" ? "modelo" : "novo");
    form.action = alvo;
  }
  window.alternarModoTreino = alternarModoTreino;

  /* --- Editar treino --- */
  window.abrirEdicaoTreino = function (id, nome, dia, ordem, notas) {
    var d = document.getElementById("form-editar-treino");
    document.getElementById("form-editar-treino-action").action = "/aluno/" + alunoId() + "/treino/" + id + "/editar";
    document.getElementById("et-nome").value = nome;
    document.getElementById("et-dia").value = dia;
    document.getElementById("et-ordem").value = ordem;
    document.getElementById("et-notas").value = notas;
    d.showModal();
  };

  /* --- Editar exercício --- */
  window.abrirEdicaoExercicio = function (id, nome, grupo, series, reps, carga, descanso, rir, obs, prog) {
    var d = document.getElementById("form-editar-exercicio");
    document.getElementById("form-editar-exercicio-action").action = "/exercicio/" + id + "/editar";
    document.getElementById("ee-nome").value = nome || "";
    document.getElementById("ee-grupo").value = grupo || "";
    document.getElementById("ee-series").value = series || "";
    document.getElementById("ee-reps").value = reps || "";
    document.getElementById("ee-carga").value = carga || "";
    document.getElementById("ee-descanso").value = descanso || "";
    document.getElementById("ee-rir").value = rir || "";
    document.getElementById("ee-obs").value = obs || "";
    document.getElementById("ee-prog").value = prog || "";
    d.showModal();
  };

  /* --- Adicionar manualmente --- */
  window.abrirManual = function (treinoId) {
    var d = document.getElementById("form-manual-exercicio");
    document.getElementById("form-manual-exercicio-action").action = "/treino/" + treinoId + "/exercicio/novo";
    d.showModal();
  };

  /* --- Duplicar treino --- */
  window.duplicarTreino = function (treinoId) {
    var d = document.getElementById("form-duplicar-treino");
    document.getElementById("form-duplicar-treino-action").action = "/treino/" + treinoId + "/duplicar";
    document.getElementById("dt-nome").value = "";
    d.showModal();
  };

  /* --- Copiar treino de outro aluno --- */
  var cpAluno = document.getElementById("cp-aluno");
  if (cpAluno && window.OUTROS_TREINOS) {
    function preencherTreinos() {
      var sel = document.getElementById("cp-treino");
      sel.innerHTML = "";
      var id = parseInt(cpAluno.value, 10);
      var alvo = null;
      window.OUTROS_TREINOS.forEach(function (o) {
        if (o.aluno.id === id) alvo = o;
      });
      if (!alvo) return;
      alvo.treinos.forEach(function (t) {
        var opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.nome + (t.dia_semana ? " (" + t.dia_semana + ")" : "");
        sel.appendChild(opt);
      });
    }
    cpAluno.addEventListener("change", preencherTreinos);
    preencherTreinos();
  }

  /* --- Assistente --- */
  var sugestaoItens = [];

  function gerarSugestao() {
    var prioridades = Array.prototype.map.call(
      document.querySelectorAll(".as-prior:checked"), function (c) { return c.value; }
    );
    var equipamentos = Array.prototype.map.call(
      document.querySelectorAll(".as-equip:checked"), function (c) { return c.value; }
    );
    var body = {
      objetivo: document.getElementById("as-objetivo").value,
      divisao: document.getElementById("as-divisao").value,
      nivel: document.getElementById("as-nivel").value,
      duracao: document.getElementById("as-duracao").value,
      prioridades: prioridades,
      restricoes: document.getElementById("as-rest").value,
      equipamentos: equipamentos,
    };
    var btnSalvar = document.querySelector('#assistente-preview .btn.primary');
    if (btnSalvar) btnSalvar.disabled = true;
    fetch("/aluno/" + alunoId() + "/assistente/sugestao", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        sugestaoItens = (d && d.itens) || [];
        var avisos = (d && d.avisos) || [];
        var av = document.getElementById("assistente-avisos");
        av.innerHTML = "";
        avisos.forEach(function (a) {
          var el = document.createElement("span");
          el.className = "rf-aviso";
          el.textContent = a;
          av.appendChild(el);
          av.appendChild(document.createElement("br"));
        });
        renderSugestao();
      });
  }
  window.gerarSugestao = gerarSugestao;

  function renderSugestao() {
    var tabela = document.getElementById("assistente-itens");
    tabela.innerHTML = "";
    sugestaoItens.forEach(function (item, i) {
      var tr = document.createElement("tr");
      tr.setAttribute("data-idx", i);
      var tdN = document.createElement("td");
      tdN.className = "strong";
      tdN.textContent = String(i + 1);
      var tdEx = document.createElement("td");
      var inpNome = document.createElement("input");
      inpNome.className = "asp-input asp-nome";
      inpNome.value = item.nome;
      tdEx.appendChild(inpNome);
      var grupo = document.createElement("div");
      grupo.className = "muted small";
      grupo.textContent = [item.grupo, item.padrao].filter(Boolean).join(" · ");
      tdEx.appendChild(grupo);
      var tdS = document.createElement("td");
      tdS.appendChild(campo(item, "series"));
      var tdR = document.createElement("td");
      tdR.appendChild(campo(item, "repeticoes"));
      var tdRir = document.createElement("td");
      tdRir.appendChild(campo(item, "rir"));
      var tdD = document.createElement("td");
      tdD.appendChild(campo(item, "descanso"));
      var tdA = document.createElement("td");
      var btnR = document.createElement("button");
      btnR.type = "button";
      btnR.className = "btn ghost danger small";
      btnR.innerHTML = '<svg class="icon"><use href="#i-x"/></svg>';
      btnR.addEventListener("click", function () {
        sugestaoItens.splice(i, 1);
        renderSugestao();
      });
      tdA.appendChild(btnR);
      tr.appendChild(tdN);
      tr.appendChild(tdEx);
      tr.appendChild(tdS);
      tr.appendChild(tdR);
      tr.appendChild(tdRir);
      tr.appendChild(tdD);
      tr.appendChild(tdA);
      tabela.appendChild(tr);
    });
    document.querySelectorAll("#assistente-itens .asp-input").forEach(function (inp) {
      inp.addEventListener("input", function () {
        var tr = inp.closest("tr");
        var idx = parseInt(tr.getAttribute("data-idx"), 10);
        var item = sugestaoItens[idx];
        if (!item) return;
        if (inp.classList.contains("asp-nome")) item.nome = inp.value;
        if (inp.classList.contains("asp-series")) item.series = inp.value;
        if (inp.classList.contains("asp-repeticoes")) item.repeticoes = inp.value;
        if (inp.classList.contains("asp-rir")) item.rir = inp.value;
        if (inp.classList.contains("asp-descanso")) item.descanso = inp.value;
      });
    });
    document.getElementById("assistente-preview").style.display = "";
    var btnSalvar = document.querySelector('#assistente-preview .btn.primary');
    if (btnSalvar) btnSalvar.disabled = false;
  }

  function campo(item, key, cls) {
    var inp = document.createElement("input");
    inp.className = "asp-input asp-" + key;
    inp.value = item[key] == null ? "" : item[key];
    return inp;
  }

  function salvarSugestao() {
    var body = {
      nome: document.getElementById("as-nome").value,
      dia_semana: document.getElementById("as-dia").value,
      notas: "",
      itens: sugestaoItens.map(function (x) {
        return {
          ex_id: x.ex_id,
          nome: x.nome,
          series: x.series,
          repeticoes: x.repeticoes,
          rir: x.rir,
          descanso: x.descanso,
          carga: x.carga || "",
          observacoes: x.observacoes || "",
        };
      }),
    };
    fetch("/aluno/" + alunoId() + "/assistente/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json(); })
      .then(function () {
        window.location.href = "/aluno/" + alunoId() + "/treino";
      });
  }
  window.salvarSugestao = salvarSugestao;
})();