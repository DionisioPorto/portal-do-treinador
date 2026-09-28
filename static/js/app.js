document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form.confirmar").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var msg = form.getAttribute("data-confirm") || "Tem certeza?";
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  document.querySelectorAll("dialog.modal").forEach(function (dlg) {
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg) dlg.close();
    });
  });

  var busca = document.getElementById("busca-alunos");
  if (busca) {
    busca.addEventListener("input", function () {
      var termo = busca.value.toLowerCase().trim();
      var total = 0;
      document.querySelectorAll(".aluno-card").forEach(function (card) {
        var texto = (card.getAttribute("data-busca") || "").toLowerCase();
        var ok = texto.indexOf(termo) !== -1;
        card.classList.toggle("hidden", !ok);
        if (ok) total += 1;
      });
      var contagem = document.getElementById("resultado-contagem");
      if (contagem) {
        contagem.textContent = termo
          ? total + " resultado(s)"
          : "Todos os alunos";
      }
    });
  }

  var toasts = document.getElementById("toasts");
  if (toasts) {
    [].forEach.call(toasts.querySelectorAll(".toast"), function (t) {
      var sair = function () {
        t.classList.add("toast-leave");
        setTimeout(function () { t.remove(); }, 350);
      };
      setTimeout(sair, 3200);
      t.addEventListener("click", sair);
    });
  }

  var picker = document.getElementById("rf-picker");
  if (picker) {
    var grupoMap = {};
    picker.querySelectorAll(".alimento-opcao").forEach(function (op) {
      var g = op.querySelector("input").getAttribute("data-grupo");
      var n = op.querySelector("input").getAttribute("data-nome");
      if (!grupoMap[g]) grupoMap[g] = [];
      grupoMap[g].push(n);
    });

    var busca = document.getElementById("rf-busca");
    if (busca) {
      busca.addEventListener("input", function () {
        var termo = busca.value.toLowerCase().trim();
        picker.querySelectorAll(".alimento-cat").forEach(function (cat) {
          var visiveis = 0;
          cat.querySelectorAll(".alimento-opcao").forEach(function (op) {
            var txt = (op.querySelector("input").getAttribute("data-nome") || "").toLowerCase();
            var ok = txt.indexOf(termo) !== -1;
            op.classList.toggle("hidden", !ok);
            if (ok) visiveis++;
          });
          cat.classList.toggle("hidden", visiveis === 0);
        });
      });
    }

    function marcadosInfo() {
      var lista = [];
      picker.querySelectorAll("input[name=alimentos]:checked").forEach(function (inp) {
        var n = (window.NUTRI || {})[inp.value] || {};
        lista.push({
          aid: Number(inp.value),
          nome: inp.getAttribute("data-nome") || n.nome || "",
          grupo: inp.getAttribute("data-grupo") || n.grupo || "",
          k: Number(n.k) || 0,
          p: Number(n.p) || 0,
          c: Number(n.c) || 0,
          g: Number(n.g) || 0,
          porcao: Number(n.porcao) || 100
        });
      });
      return lista;
    }

    function metasRefeicao() {
      function val(id) {
        var el = document.getElementById(id);
        var v = el ? parseFloat(el.value) : 0;
        return isNaN(v) ? 0 : v;
      }
      return [val("rf-calorias"), val("rf-proteinas"), val("rf-carbs"), val("rf-gorduras")];
    }

    function setQtdInputs(gramas) {
      var alvo = document.getElementById("rf-qtds");
      if (!alvo) return;
      alvo.innerHTML = "";
      gramas.forEach(function (x) {
        var inp = document.createElement("input");
        inp.type = "hidden";
        inp.name = "alimento_qtd";
        inp.value = x.aid + ":" + Math.max(0, Math.round(x.qtd));
        alvo.appendChild(inp);
      });
    }

    function mostrarTotaisGramas(gramas) {
      var pre = document.getElementById("rf-previsao");
      if (!pre) return;
      var k = 0, p = 0, c = 0, g = 0;
      gramas.forEach(function (x) {
        var w = x.qtd / 100;
        k += x.k * w; p += x.p * w; c += x.c * w; g += x.g * w;
      });
      var m = metasRefeicao();
      var partes = ["<strong>" + Math.round(k) + " kcal</strong>",
        "prot " + Math.round(p) + " g", "carb " + Math.round(c) + " g", "gord " + Math.round(g) + " g"];
      var temMeta = m.some(function (v) { return v > 0; });
      if (temMeta) {
        var dif = Math.round(k - m[0]);
        partes.push("meta: " + Math.round(m[0]) + " kcal · P " + Math.round(m[1]) +
          " · C " + Math.round(m[2]) + " · G " + Math.round(m[3]));
        partes.push((dif <= 2 && dif >= -2) ? "kcal ok" : "dif. " + (dif > 0 ? "+" : "") + dif + " kcal");
      }
      pre.innerHTML = "Total: " + partes.join(" &middot; ");
      pre.style.display = "block";
    }

    function renderSugestoes(gramas) {
      var box = document.getElementById("rf-sugestoes");
      if (!box) return;
      box.innerHTML = "";
      if (!gramas.length) {
        box.innerHTML = '<span class="muted">Marque um alimento para ver as substituições e as gramas calculadas.</span>';
        return;
      }
      gramas.forEach(function (x, i) {
        var subs = (grupoMap[x.grupo] || []).filter(function (n) { return n !== x.nome; });
        var linha = document.createElement("div");
        linha.className = "rf-sugestao" + (i ? "" : " first");
        var q = Math.max(0, Math.round(x.qtd));
        var base = '<span class="rf-sugestao-nome">' + x.nome + "</span> <strong class=\"food-qtd\">" + q + " g</strong>";
        if (subs.length) {
          linha.innerHTML = base + " &middot; Substitua por: " + subs.map(function (n) {
            return "<strong>" + n + "</strong>";
          }).join(", ");
        } else {
          linha.innerHTML = base + " <span class=\"muted\">(sem substituto no catálogo)</span>";
        }
        box.appendChild(linha);
      });
    }

    window.calcularGramasJS = async function (itens, kcalT, pT, cT, gT) {
      kcalT = parseFloat(kcalT) || 0;
      pT = parseFloat(pT) || 0;
      cT = parseFloat(cT) || 0;
      gT = parseFloat(gT) || 0;
      try {
        var resp = await fetch("/refeicao/calcular", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            itens: itens.map(function (x) { return { aid: x.aid, qtd: 0 }; }),
            macros: [kcalT, pT, cT, gT]
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        var dados = await resp.json();
        var lista = (dados && dados.itens) || [];
        window.__rf_avisos = (dados && dados.avisos) || [];
        lista.forEach(function (x) { x.qtd = Number(x.qtd) || 0; });
        return lista;
      } catch (e) {
        window.__rf_avisos = ["Não foi possível recalcular no servidor; usando porções padrão."];
        return itens.map(function (x) { return Object.assign({}, x, { qtd: x.porcao }); });
      }
    };

    async function recalcularGramas() {
      var itens = marcadosInfo();
      var pre = document.getElementById("rf-previsao");
      if (!itens.length) {
        renderSugestoes([]);
        if (pre) pre.style.display = "none";
        setQtdInputs([]);
        return;
      }
      var m = metasRefeicao();
      var temMeta = m.some(function (v) { return v > 0; });
      var gramas = temMeta
        ? await window.calcularGramasJS(itens, m[0], m[1], m[2], m[3])
        : itens.map(function (x) { return Object.assign({}, x, { qtd: x.porcao }); });
      renderSugestoes(gramas);
      mostrarTotaisGramas(gramas);
      setQtdInputs(gramas);
      var avisos = window.__rf_avisos || [];
      if (avisos.length && pre) {
        var avHtml = avisos.map(function (a) {
          return '<span class="rf-aviso">' + a + "</span>";
        }).join("<br>");
        pre.innerHTML = pre.innerHTML + "<br>" + avHtml;
      }
    }

    window.aplicarGramasSalvas = function (qtdMap) {
      var itens = marcadosInfo();
      itens.forEach(function (x) {
        if (qtdMap[x.nome] != null) x.qtd = Number(qtdMap[x.nome]) || x.qtd;
      });
      renderSugestoes(itens);
      mostrarTotaisGramas(itens);
      setQtdInputs(itens);
    };

    ["rf-calorias", "rf-proteinas", "rf-carbs", "rf-gorduras"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", recalcularGramas);
    });

    picker.addEventListener("change", function (e) {
      if (e.target && e.target.name === "alimentos") recalcularGramas();
    });
    window.recalcularGramas = recalcularGramas;
  }
});

function abrirNovaRefeicao() {
  var form = document.getElementById("form-refeicao-form");
  if (form) form.action = form.getAttribute("data-novo-url") || form.action;
  var titulo = document.getElementById("form-refeicao-titulo");
  if (titulo) titulo.textContent = "Nova refeição";
  var ids = ["rf-nome", "rf-horario", "rf-calorias", "rf-proteinas", "rf-carbs", "rf-gorduras", "rf-descricao", "rf-busca"];
  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.value = "";
  });
  document.querySelectorAll("#form-refeicao input[name=alimentos]").forEach(function (inp) {
    inp.checked = false;
  });
  var busca = document.getElementById("rf-busca");
  if (busca) busca.dispatchEvent(new Event("input"));
  if (window.recalcularGramas) window.recalcularGramas();
}

function abrirEdicaoRefeicao(id) {
  if (!window.REFEICOES || !REFEICOES[id]) return;
  var r = REFEICOES[id];
  var form = document.getElementById("form-refeicao-form");
  if (form) form.action = "/refeicao/" + id + "/editar";
  var titulo = document.getElementById("form-refeicao-titulo");
  if (titulo) titulo.textContent = "Editar refeição";
  document.getElementById("rf-nome").value = r.nome || "";
  document.getElementById("rf-horario").value = r.horario || "";
  document.getElementById("rf-calorias").value = r.calorias || "";
  document.getElementById("rf-proteinas").value = r.proteinas || "";
  document.getElementById("rf-carbs").value = r.carbs || "";
  document.getElementById("rf-gorduras").value = r.gorduras || "";
  document.getElementById("rf-descricao").value = r.descricao || "";
  var busca = document.getElementById("rf-busca");
  if (busca) busca.value = "";
  var marcados = (r.alimentos || []).map(function (n) { return n.toLowerCase(); });
  document.querySelectorAll("#form-refeicao input[name=alimentos]").forEach(function (inp) {
    var ehMarcado = marcados.indexOf((inp.getAttribute("data-nome") || "").toLowerCase()) !== -1;
    inp.checked = ehMarcado;
  });
  if (busca) busca.dispatchEvent(new Event("input"));
  if (window.aplicarGramasSalvas) window.aplicarGramasSalvas(r.alim_qtd || {});
  document.getElementById("form-refeicao").showModal();
}