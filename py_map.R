py1 <- list.files(path="scripts", pattern=".*\\.py", full.names = TRUE)
py2 <- list.files(path="src", pattern=".*\\.py", full.names = TRUE)
py <- tibble(file=c(py1, py2)) |> mutate(code=map(file, readLines)) |> unnest(code) |>
  filter(code!="") |>
  mutate(iscol1=str_detect(code, "^\\s+", negate=TRUE),
         fun=str_extract(code, "^def\\s+.*") |>
           str_remove("^def\\s+") |> str_remove("\\(.*$")) |>
  mutate(fun=if_else(iscol1 & is.na(fun), "---", fun)) |>
  fill(fun) |> filter(fun != "---") |>
  filter(str_detect(code, "\\s*#", negate=TRUE)) |>
  select(file, fun, code)
# View(py)

funs <- py |> distinct(file, fun) |> filter(fun!="main")
funs |> add_count(fun) |> filter(n>1) ## check to make sure functions not defined twice

findfun <- \(fun) {
  py |>
    filter(str_detect(.data$code, "^def", negate = TRUE)) |>
    filter(str_detect(.data$code, .env$fun)) |>
    rename(by.file="file", by.fun="fun")
}

pymap <- funs |> mutate(code=map(fun, findfun)) |> unnest(code) |>
  mutate(n=length(unique(by.file)), .by=fun) |>
  mutate(self=!(n>1 | file!=by.file)) #|> select(-code, -n)


bind_rows(
  funs |> anti_join(pymap),
  pymap |> filter(self))
pymap |> filter(!self) |> select(-self) |> writexl::write_xlsx("pymap-orig.xlsx")
